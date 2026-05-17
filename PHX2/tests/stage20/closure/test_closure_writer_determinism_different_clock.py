"""Stage 20.4 Phase 6 -- different-clock determinism harness.

Locked invariants:

  * Two orchestrator runs over the same semantic config with two
    DIFFERENT injected clocks and two distinct ``output_root``
    parents must produce:

      - Byte-identical content for the four "stable" artifacts
        whose payload does NOT depend on run_id / timestamps:
          * codebase_audit_report.json
          * stage20_2_lineage.json
          * stage20_3_lineage.json
          * stage20_closure_checklist.csv

      - Per-clock-varying content for the four "timestamp-bearing"
        artifacts, which may differ ONLY in run_id /
        generated_at_utc / timestamp fields:
          * stage20_closure_manifest.json
          * stage20_4_run.log
          * stage21_handoff.md
          * README.md

  * No other field of those four files may differ between the two
    runs. The test enforces this by normalizing the per-run
    run_id and generated_at_utc out of each file, then comparing
    the normalized bytes.

  * The two runs do not bypass E2046: different clocks -> different
    run_ids -> distinct run directories under separate output_roots.
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


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
_STAGE20_2_CLEAN_SRC = _FIXTURES_ROOT / "stage20_2_clean"
_STAGE20_3_CLEAN_SRC = _FIXTURES_ROOT / "stage20_3_clean"

_VALID_SHA_20_1 = "c57606779c76763bdb0be6ee5f93cf44db99a29f"
_VALID_SHA_20_2 = "a60bbd4174a8169e90744bcff8a68ebd43a99a62"
_VALID_SHA_20_3 = "31b131a1bf6322f6c533adf9c9431eb7e68f25c9"


_FROZEN_DT_A = datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc)
_FROZEN_DT_B = datetime(2026, 9, 9, 1, 2, 3, tzinfo=timezone.utc)


def _clock_a() -> FrozenClock:
    return FrozenClock(_FROZEN_DT_A)


def _clock_b() -> FrozenClock:
    return FrozenClock(_FROZEN_DT_B)


STABLE_ARTIFACTS = (
    "codebase_audit_report.json",
    "stage20_2_lineage.json",
    "stage20_3_lineage.json",
    "stage20_closure_checklist.csv",
)


VARYING_ARTIFACTS = (
    "stage20_closure_manifest.json",
    "stage20_4_run.log",
    "stage21_handoff.md",
    "README.md",
)


def _build_layout(parent: Path) -> dict:
    s2 = parent / "stage20_2"
    s3 = parent / "stage20_3"
    shutil.copytree(_STAGE20_2_CLEAN_SRC, s2)
    shutil.copytree(_STAGE20_3_CLEAN_SRC, s3)
    repo = parent / "repo"
    (repo / "PHX2" / "stage20" / "closure").mkdir(parents=True)
    return {"s2": s2, "s3": s3, "repo": repo}


def _write_config(parent: Path, layout: dict, output_root: Path) -> Path:
    cfg = {
        "stage20_1_commit_sha": _VALID_SHA_20_1,
        "stage20_2_commit_sha": _VALID_SHA_20_2,
        "stage20_3_commit_sha": _VALID_SHA_20_3,
        "stage20_2_run_dir": str(layout["s2"]),
        "stage20_3_run_dir": str(layout["s3"]),
        "repo_root": str(layout["repo"]),
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
    p = parent / "config.json"
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return p


def _locate_run_dir(output_root: Path) -> Path:
    closure_runs = output_root / "stage20_closure_runs"
    children = sorted(closure_runs.iterdir())
    assert len(children) == 1
    return children[0]


@pytest.fixture
def two_clock_runs(tmp_path: Path) -> dict:
    """Run the orchestrator twice with different clocks, against the
    same source layout, into two distinct output_roots.

    Because compute_config_sha8 is invariant across clock changes,
    config_sha8 is the same for both runs and differences in run_id
    come solely from the utc_compact field of the run-id template.
    """
    parent_a = tmp_path / "tree_a"
    parent_b = tmp_path / "tree_b"
    parent_a.mkdir()
    parent_b.mkdir()

    # Two distinct output_roots and a shared, declared root used
    # only to keep config_sha8 identical across the two runs.
    declared_root = tmp_path / "declared_output_root"
    declared_root.mkdir()

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_a.mkdir()
    out_b.mkdir()

    # Source dirs (s2, s3, repo) under tree_a; both configs use the
    # same paths so config_sha8 matches.
    layout_a = _build_layout(parent_a)
    # tree_b parent kept distinct only to demonstrate separation of
    # working dirs; both configs point at tree_a's source files.
    cfg_dict = {
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
    cfg_path_a.write_text(
        json.dumps(cfg_dict, indent=2), encoding="utf-8",
    )
    cfg_path_b.write_text(
        json.dumps(cfg_dict, indent=2), encoding="utf-8",
    )

    rc_a = ro.run_closure(
        cfg_path_a, clock=_clock_a(), output_root_override=out_a,
    )
    rc_b = ro.run_closure(
        cfg_path_b, clock=_clock_b(), output_root_override=out_b,
    )
    assert rc_a == 0
    assert rc_b == 0

    run_a = _locate_run_dir(out_a)
    run_b = _locate_run_dir(out_b)

    return {
        "out_a": out_a, "out_b": out_b,
        "run_a": run_a, "run_b": run_b,
    }


# ---------------------------------------------------------------------------
# Stable artifacts must be byte-identical across clock change
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", list(STABLE_ARTIFACTS))
def test_stable_artifact_is_byte_identical_across_clock_change(
    two_clock_runs, filename,
):
    a_bytes = (two_clock_runs["run_a"] / filename).read_bytes()
    b_bytes = (two_clock_runs["run_b"] / filename).read_bytes()
    assert a_bytes == b_bytes, (
        f"different-clock determinism failed: stable artifact "
        f"{filename} differs (lengths {len(a_bytes)} vs {len(b_bytes)})"
    )


# ---------------------------------------------------------------------------
# Varying artifacts: run_ids differ (so we know the test scenario is real)
# ---------------------------------------------------------------------------


def test_run_ids_differ_between_two_clocks(two_clock_runs):
    """Sanity: different clocks must produce different run_ids
    (utc_compact differs)."""
    assert two_clock_runs["run_a"].name != two_clock_runs["run_b"].name


def test_run_ids_share_config_sha8_suffix(two_clock_runs):
    """The trailing 8-char config_sha8 must MATCH (compute_config_sha8
    is invariant across clock changes per its locked spec)."""
    a_suffix = two_clock_runs["run_a"].name.rsplit("_", 1)[-1]
    b_suffix = two_clock_runs["run_b"].name.rsplit("_", 1)[-1]
    assert a_suffix == b_suffix


# ---------------------------------------------------------------------------
# Varying artifacts: differences are CONFINED to run_id + generated_at_utc
# ---------------------------------------------------------------------------


def _normalize(text: str, run_id: str, generated_at_utc: str) -> str:
    """Replace per-run identifiers with placeholders so two
    normalized outputs can be byte-compared."""
    return (
        text
        .replace(run_id, "<RUN_ID>")
        .replace(generated_at_utc, "<GENERATED_AT_UTC>")
    )


def test_manifest_differs_only_in_run_id_and_timestamp(two_clock_runs):
    """After substituting run_id + generated_at_utc with placeholders,
    the two manifests must be byte-identical."""
    a_text = (
        two_clock_runs["run_a"] / "stage20_closure_manifest.json"
    ).read_text(encoding="utf-8")
    b_text = (
        two_clock_runs["run_b"] / "stage20_closure_manifest.json"
    ).read_text(encoding="utf-8")

    a_manifest = json.loads(a_text)
    b_manifest = json.loads(b_text)

    a_norm = _normalize(
        a_text, a_manifest["run_id"], a_manifest["generated_at_utc"],
    )
    b_norm = _normalize(
        b_text, b_manifest["run_id"], b_manifest["generated_at_utc"],
    )
    assert a_norm == b_norm


def test_run_log_differs_only_in_run_id_and_timestamp(two_clock_runs):
    a_text = (
        two_clock_runs["run_a"] / "stage20_4_run.log"
    ).read_text(encoding="utf-8")
    b_text = (
        two_clock_runs["run_b"] / "stage20_4_run.log"
    ).read_text(encoding="utf-8")

    a_events = [json.loads(line) for line in a_text.splitlines() if line]
    b_events = [json.loads(line) for line in b_text.splitlines() if line]
    # Both logs share a single ts value per the locked design.
    a_ts = a_events[0]["ts"]
    b_ts = b_events[0]["ts"]
    a_run_id = a_events[0]["run_id"]
    b_run_id = b_events[0]["run_id"]

    a_norm = _normalize(a_text, a_run_id, a_ts)
    b_norm = _normalize(b_text, b_run_id, b_ts)
    assert a_norm == b_norm


def test_handoff_md_differs_only_in_run_id_and_timestamp(two_clock_runs):
    a_text = (
        two_clock_runs["run_a"] / "stage21_handoff.md"
    ).read_text(encoding="utf-8")
    b_text = (
        two_clock_runs["run_b"] / "stage21_handoff.md"
    ).read_text(encoding="utf-8")

    a_run_id = two_clock_runs["run_a"].name
    b_run_id = two_clock_runs["run_b"].name
    # Pull the iso timestamps out of the manifest (they're stable
    # across artifacts in a single run).
    a_manifest = json.loads(
        (two_clock_runs["run_a"] / "stage20_closure_manifest.json")
        .read_text(encoding="utf-8")
    )
    b_manifest = json.loads(
        (two_clock_runs["run_b"] / "stage20_closure_manifest.json")
        .read_text(encoding="utf-8")
    )
    a_norm = _normalize(a_text, a_run_id, a_manifest["generated_at_utc"])
    b_norm = _normalize(b_text, b_run_id, b_manifest["generated_at_utc"])
    assert a_norm == b_norm


def test_readme_differs_only_in_run_id_and_timestamp(two_clock_runs):
    a_text = (
        two_clock_runs["run_a"] / "README.md"
    ).read_text(encoding="utf-8")
    b_text = (
        two_clock_runs["run_b"] / "README.md"
    ).read_text(encoding="utf-8")
    a_run_id = two_clock_runs["run_a"].name
    b_run_id = two_clock_runs["run_b"].name
    a_manifest = json.loads(
        (two_clock_runs["run_a"] / "stage20_closure_manifest.json")
        .read_text(encoding="utf-8")
    )
    b_manifest = json.loads(
        (two_clock_runs["run_b"] / "stage20_closure_manifest.json")
        .read_text(encoding="utf-8")
    )
    a_norm = _normalize(a_text, a_run_id, a_manifest["generated_at_utc"])
    b_norm = _normalize(b_text, b_run_id, b_manifest["generated_at_utc"])
    assert a_norm == b_norm


# ---------------------------------------------------------------------------
# Stable + varying coverage: every artifact accounted for
# ---------------------------------------------------------------------------


def test_stable_and_varying_partition_covers_all_artifacts():
    from PHX2.stage20.closure.constants import (
        CLOSURE_OUTPUT_ARTIFACT_FILENAMES,
    )
    covered = set(STABLE_ARTIFACTS) | set(VARYING_ARTIFACTS)
    assert covered == set(CLOSURE_OUTPUT_ARTIFACT_FILENAMES)


# ---------------------------------------------------------------------------
# Defense: stable artifact bytes ALSO match by sha256
# ---------------------------------------------------------------------------


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_stable_artifact_sha256_matches_across_clock_change(two_clock_runs):
    a_hashes = {
        name: _sha256((two_clock_runs["run_a"] / name).read_bytes())
        for name in STABLE_ARTIFACTS
    }
    b_hashes = {
        name: _sha256((two_clock_runs["run_b"] / name).read_bytes())
        for name in STABLE_ARTIFACTS
    }
    assert a_hashes == b_hashes
