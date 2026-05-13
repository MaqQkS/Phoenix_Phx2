"""Phase 8: manifest carries every Stage 15 lineage hash and the runtime policy hash matches the body."""

from __future__ import annotations

import json
from pathlib import Path

from PHX2.stage16a.cli import (
    MANIFEST_FILENAME,
    RUN_LOG_FILENAME,
    RUNTIME_POLICY_FILENAME,
    main as cli_main,
)
from PHX2.stage16a.hashing import sha256_file
from PHX2.stage16a.runtime_policy_builder import STAGE15_LINEAGE_PASSTHROUGH_FIELDS
from PHX2.tests.stage16a.fixtures.builders import build_stage15_run_dir


def _run_clean(tmp_path: Path) -> tuple[Path, dict]:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    out = tmp_path / "out"
    rc = cli_main(
        [
            "--stage15-run-path", str(s15),
            "--output-dir", str(out),
        ]
    )
    assert rc == 0
    manifest = json.loads(
        (out / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    return out, manifest


def test_manifest_carries_stage15_run_hashes(tmp_path: Path) -> None:
    out, manifest = _run_clean(tmp_path)
    assert manifest["source_stage15_run_path"]
    assert manifest["source_stage15_manifest_hash"].startswith("sha256:")
    assert manifest["source_stage15_policy_draft_hash"].startswith("sha256:")


def test_manifest_passes_through_every_stage15_lineage_field(tmp_path: Path) -> None:
    out, manifest = _run_clean(tmp_path)
    passthrough = manifest["stage15_lineage_passthrough"]
    for fld in STAGE15_LINEAGE_PASSTHROUGH_FIELDS:
        assert fld in passthrough, f"missing {fld!r} in stage15_lineage_passthrough"
        assert passthrough[fld] != ""


def test_manifest_rule_counts(tmp_path: Path) -> None:
    out, manifest = _run_clean(tmp_path)
    assert manifest["input_stage15_approved_rule_count"] == 1
    assert manifest["output_runtime_rule_count"] == 1


def test_manifest_runtime_policy_hash_matches_body(tmp_path: Path) -> None:
    """``output_runtime_policy_hash`` records the policy_hash from the
    runtime artifact body (NOT the on-disk file hash of the rendered JSON).
    These are intentionally different surfaces: the body hash is over
    compact canonical JSON sans policy_hash; the file hash is over the
    pretty-printed bytes."""

    out, manifest = _run_clean(tmp_path)
    body = json.loads(
        (out / RUNTIME_POLICY_FILENAME).read_text(encoding="utf-8")
    )
    assert manifest["output_runtime_policy_hash"] == body["policy_hash"]


def test_manifest_output_files_hashes_match_disk(tmp_path: Path) -> None:
    out, manifest = _run_clean(tmp_path)
    output_files = manifest["output_files"]
    for fname in (RUNTIME_POLICY_FILENAME, RUN_LOG_FILENAME):
        assert fname in output_files
        assert output_files[fname] == sha256_file(out / fname)


def test_manifest_safety_surfaces_recorded(tmp_path: Path) -> None:
    out, manifest = _run_clean(tmp_path)

    s15_surface = manifest["safety_surface_input_stage15"]
    assert s15_surface["hard_block_allowed"] is False
    assert s15_surface["enforcement_mode"] == "NONE"
    assert s15_surface["safe_for_observe_only_wiring"] is True

    runtime_surface = manifest["safety_surface_output_runtime"]
    assert runtime_surface["enforcement_mode"] == "OBSERVE_ONLY"
    assert runtime_surface["hard_block_allowed"] is False
    assert runtime_surface["runtime_consumable"] is True
    assert runtime_surface["allowed_action_set"] == ["LOG_WOULD_BLOCK"]
