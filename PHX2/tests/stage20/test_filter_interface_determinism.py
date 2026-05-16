"""Stage 20.3 Phase 6 determinism harness.

End-to-end byte-identical determinism, run-id stability under
repeated derivation, run-id divergence on input change, and
manifest serialization stability.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from PHX2.stage20.clock import FrozenClock
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.filter_interface_input import Stage20TwoInputs
from PHX2.stage20.filter_interface_runner import run_stage20_3
from PHX2.stage20.stage20_3_manifest import (
    assemble_stage20_3_manifest,
    derive_stage20_3_run_id,
)

from PHX2.tests.stage20.fixtures_stage20_2_synthetic import (
    build_synthetic_stage20_2_run,
)


def _frozen() -> FrozenClock:
    return FrozenClock(
        datetime(2026, 5, 15, 12, 34, 56, tzinfo=timezone.utc)
    )


def _file_sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# D1: full-pipeline byte-identical determinism
# ---------------------------------------------------------------------------


def test_d1_full_pipeline_byte_identical_across_two_tmp_paths(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    run_a = build_synthetic_stage20_2_run(dir_a, candidate_count=5)
    run_b = build_synthetic_stage20_2_run(dir_b, candidate_count=5)
    res_a = run_stage20_3(run_a, clock=_frozen())
    res_b = run_stage20_3(run_b, clock=_frozen())
    for fn in (
        "stage20_3_manifest.json",
        "filter_interface_registry.csv",
        "filter_interface_results.csv",
        "stage20_3_run.log",
        "README.md",
    ):
        sha_a = _file_sha(res_a.stage20_3_run_dir / fn)
        sha_b = _file_sha(res_b.stage20_3_run_dir / fn)
        assert sha_a == sha_b, (
            f"artifact {fn} bytes differ across tmp_paths: "
            f"sha_a={sha_a} sha_b={sha_b}"
        )


# ---------------------------------------------------------------------------
# D2: run-id stability under repeated derivation
# ---------------------------------------------------------------------------


def test_d2_run_id_stable_across_100_repeated_calls():
    results = {
        derive_stage20_3_run_id("rid_stable", "h" * 64)
        for _ in range(100)
    }
    assert len(results) == 1


# ---------------------------------------------------------------------------
# D3: run-id divergence on input change
# ---------------------------------------------------------------------------


def test_d3a_run_id_diverges_when_stage20_run_id_varies():
    a = derive_stage20_3_run_id("rid_a", "h" * 64)
    b = derive_stage20_3_run_id("rid_b", "h" * 64)
    assert a != b


def test_d3b_run_id_diverges_when_manifest_sha_varies():
    a = derive_stage20_3_run_id("rid_x", "h" * 64)
    b = derive_stage20_3_run_id("rid_x", "k" * 64)
    assert a != b


# ---------------------------------------------------------------------------
# D4: manifest serialization stability
# ---------------------------------------------------------------------------


def _synth_inputs() -> Stage20TwoInputs:
    return Stage20TwoInputs(
        stage20_2_run_dir=__import__("pathlib").Path("synthetic"),
        stage20_run_id="synth_rid",
        manifest={"k": "v"},
        manifest_json_sha256="a" * 64,
        preview_candidates_csv_sha256="b" * 64,
        alert_eligibility_decisions_csv_sha256="c" * 64,
        readme_md_sha256="d" * 64,
        stage20_run_log_sha256="e" * 64,
        label_mapping={},
    )


def test_d4_manifest_dict_serializes_byte_stably():
    common = dict(
        inputs=_synth_inputs(),
        stage20_3_run_id="abcdef0123456789",
        generated_at_utc="2026-05-15T12:34:56Z",
        filter_interface_registry_csv_sha256="r" * 64,
        filter_interface_results_csv_sha256="s" * 64,
        stage20_3_run_log_sha256="l" * 64,
        readme_md_sha256="m" * 64,
    )
    a = assemble_stage20_3_manifest(**common)
    b = assemble_stage20_3_manifest(**common)
    ba = json.dumps(
        a, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8") + b"\n"
    bb = json.dumps(
        b, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8") + b"\n"
    assert ba == bb


# ---------------------------------------------------------------------------
# D5: re-run refusal locks the on-disk artifact's determinism
# ---------------------------------------------------------------------------


def test_d5_second_run_in_same_dir_raises_e2027(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    run_stage20_3(run_dir, clock=_frozen())
    with pytest.raises(Stage20ValidationError) as exc_info:
        run_stage20_3(run_dir, clock=_frozen())
    assert exc_info.value.code == "E2027"
