"""Stage 20.3 Phase 4 tests -- artifact writers.

Covers each writer in isolation. Byte-level assertions where the
spec locks the on-disk shape.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import pathlib

import pytest

from PHX2.stage20 import filter_interface_writers
from PHX2.stage20.constants import (
    FILTER_INTERFACE_REGISTRY_COLUMNS,
    FILTER_INTERFACE_RESULTS_COLUMNS,
    FILTER_REGISTRY_CONTRACT_VERSION,
    FILTER_RESULT_CONTRACT_VERSION,
)
from PHX2.stage20.filter_interface_models import (
    FilterDefinition,
    FilterEvaluationRow,
)
from PHX2.stage20.filter_interface_writers import (
    STAGE20_3_README_TEMPLATE,
    _compute_file_sha256,
    write_filter_interface_registry_csv,
    write_filter_interface_results_csv,
    write_stage20_3_manifest_json,
    write_stage20_3_readme,
    write_stage20_3_run_log,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_BOM = bytes([0xEF, 0xBB, 0xBF])


def _forbidden_fim_token() -> str:
    return "filter_" + "interface_" + "manifest"


def _make_definition(**overrides) -> FilterDefinition:
    base = dict(
        filter_id="f_001",
        filter_name="synth_filter",
        filter_version="v0.0.1",
        threshold_version="t0.0.1",
        mode="OBSERVE_ONLY",
        contract_version=FILTER_REGISTRY_CONTRACT_VERSION,
    )
    base.update(overrides)
    return FilterDefinition(**base)


def _make_row(**overrides) -> FilterEvaluationRow:
    base = dict(
        candidate_id="cand_001",
        filter_id="f_001",
        filter_name="synth_filter",
        filter_version="v0.0.1",
        threshold_version="t0.0.1",
        mode="OBSERVE_ONLY",
        evaluation_status="OBSERVED",
        observation_label="no_op",
        observation_detail_json="{}",
        contract_version=FILTER_RESULT_CONTRACT_VERSION,
    )
    base.update(overrides)
    return FilterEvaluationRow(**base)


# ---------------------------------------------------------------------------
# W1-W5: empty registry CSV
# ---------------------------------------------------------------------------


def test_w1_empty_registry_csv_single_line_with_newline(tmp_path):
    p = tmp_path / "filter_interface_registry.csv"
    write_filter_interface_registry_csv(p, ())
    raw = p.read_bytes()
    # Exactly one logical line (header) ending in "\n".
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1


def test_w2_empty_registry_csv_header_equals_locked_columns(tmp_path):
    p = tmp_path / "filter_interface_registry.csv"
    write_filter_interface_registry_csv(p, ())
    line = p.read_text(encoding="utf-8").splitlines()[0]
    assert line == ",".join(FILTER_INTERFACE_REGISTRY_COLUMNS)


def test_w3_empty_registry_csv_no_carriage_return(tmp_path):
    p = tmp_path / "filter_interface_registry.csv"
    write_filter_interface_registry_csv(p, ())
    raw = p.read_bytes()
    assert b"\r" not in raw


def test_w4_empty_registry_csv_no_bom(tmp_path):
    p = tmp_path / "filter_interface_registry.csv"
    write_filter_interface_registry_csv(p, ())
    raw = p.read_bytes()
    assert not raw.startswith(_BOM)


def test_w5_empty_registry_csv_returned_sha_matches_file(tmp_path):
    p = tmp_path / "filter_interface_registry.csv"
    sha = write_filter_interface_registry_csv(p, ())
    assert sha == hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# W6-W9: empty results CSV
# ---------------------------------------------------------------------------


def test_w6_empty_results_csv_single_line_with_newline(tmp_path):
    p = tmp_path / "filter_interface_results.csv"
    write_filter_interface_results_csv(p, ())
    raw = p.read_bytes()
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1


def test_w7_empty_results_csv_header_equals_locked_columns(tmp_path):
    p = tmp_path / "filter_interface_results.csv"
    write_filter_interface_results_csv(p, ())
    line = p.read_text(encoding="utf-8").splitlines()[0]
    assert line == ",".join(FILTER_INTERFACE_RESULTS_COLUMNS)


def test_w8_empty_results_csv_no_cr_no_bom(tmp_path):
    p = tmp_path / "filter_interface_results.csv"
    write_filter_interface_results_csv(p, ())
    raw = p.read_bytes()
    assert b"\r" not in raw
    assert not raw.startswith(_BOM)


def test_w9_empty_results_csv_sha_matches_file(tmp_path):
    p = tmp_path / "filter_interface_results.csv"
    sha = write_filter_interface_results_csv(p, ())
    assert sha == hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# W10-W14: non-empty CSV defense-in-depth
# ---------------------------------------------------------------------------


def test_w10_registry_csv_with_one_definition_two_lines(tmp_path):
    p = tmp_path / "filter_interface_registry.csv"
    write_filter_interface_registry_csv(p, (_make_definition(),))
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_w11_registry_data_row_six_columns(tmp_path):
    p = tmp_path / "filter_interface_registry.csv"
    write_filter_interface_registry_csv(p, (_make_definition(),))
    with p.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows[1]) == 6


def test_w12_results_csv_with_one_row_two_lines(tmp_path):
    p = tmp_path / "filter_interface_results.csv"
    write_filter_interface_results_csv(p, (_make_row(),))
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_w13_results_data_row_ten_columns(tmp_path):
    p = tmp_path / "filter_interface_results.csv"
    write_filter_interface_results_csv(p, (_make_row(),))
    with p.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows[1]) == 10


def test_w14_results_observation_detail_json_round_trips(tmp_path):
    p = tmp_path / "filter_interface_results.csv"
    write_filter_interface_results_csv(p, (_make_row(),))
    with p.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    odj_index = FILTER_INTERFACE_RESULTS_COLUMNS.index(
        "observation_detail_json"
    )
    # Round-trip preserves the JSON content "{}".
    assert rows[1][odj_index] == "{}"


# ---------------------------------------------------------------------------
# W15-W19: manifest JSON
# ---------------------------------------------------------------------------


def _synthetic_manifest_dict() -> dict:
    return {
        "stage20_3_minor_version": "20.3",
        "stage20_version": "stage20_v0_observe_only",
        "safe_for_live_dispatch": False,
        "live_dispatch_ready": False,
        "registered_filter_count": 0,
        "notes": ["a note"],
    }


def test_w15_manifest_json_byte_identical_across_two_writes(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    m = _synthetic_manifest_dict()
    write_stage20_3_manifest_json(a, m)
    write_stage20_3_manifest_json(b, m)
    assert a.read_bytes() == b.read_bytes()


def test_w16_manifest_json_ends_with_single_newline_no_cr(tmp_path):
    p = tmp_path / "m.json"
    write_stage20_3_manifest_json(p, _synthetic_manifest_dict())
    raw = p.read_bytes()
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\r\n")
    assert b"\r" not in raw


def test_w17_manifest_json_sort_keys_byte_stable(tmp_path):
    p = tmp_path / "m.json"
    m = _synthetic_manifest_dict()
    write_stage20_3_manifest_json(p, m)
    re_serialized = json.dumps(
        json.loads(p.read_text(encoding="utf-8")),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"
    assert re_serialized.encode("utf-8") == p.read_bytes()


def test_w18_manifest_json_ensure_ascii_false_emits_utf8_multibyte(
    tmp_path,
):
    p = tmp_path / "m.json"
    m = dict(_synthetic_manifest_dict())
    # Test-only synthetic notes; production V0_NOTE is ASCII only.
    m["notes"] = ["café"]
    write_stage20_3_manifest_json(p, m)
    raw = p.read_bytes()
    # UTF-8 encoding of "café" is c3 a9; \uXXXX would be 6 ASCII chars.
    assert b"\xc3\xa9" in raw
    assert b"\\u00e9" not in raw


def test_w19_manifest_json_no_bom(tmp_path):
    p = tmp_path / "m.json"
    write_stage20_3_manifest_json(p, _synthetic_manifest_dict())
    assert not p.read_bytes().startswith(_BOM)


# ---------------------------------------------------------------------------
# W20-W22: run log
# ---------------------------------------------------------------------------


def _events_a() -> list[dict]:
    return [
        {"event": "run_started", "ts_utc": "2026-05-15T00:00:00Z",
         "stage20_3_run_id": "0123456789abcdef",
         "detail": {"k": 1}},
        {"event": "run_completed", "ts_utc": "2026-05-15T00:00:00Z",
         "stage20_3_run_id": "0123456789abcdef",
         "detail": {"ok": True}},
    ]


def test_w20_same_event_list_twice_identical_sha(tmp_path):
    a = tmp_path / "a.log"
    b = tmp_path / "b.log"
    sha_a = write_stage20_3_run_log(a, _events_a())
    sha_b = write_stage20_3_run_log(b, _events_a())
    assert sha_a == sha_b


def test_w21_event_ordering_preserved(tmp_path):
    p = tmp_path / "run.log"
    events = _events_a()
    write_stage20_3_run_log(p, events)
    lines = p.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [e["event"] for e in parsed] == [
        "run_started", "run_completed",
    ]


def test_w22_run_log_format_matches_stage20_2_pattern(tmp_path):
    # Build a Stage 20.2 fixture log via the synthetic fixture and
    # confirm its line shape matches Stage 20.3's.
    from PHX2.tests.stage20.fixtures_stage20_2_synthetic import (
        build_synthetic_stage20_2_run,
    )
    run_dir = build_synthetic_stage20_2_run(tmp_path / "synth")
    log_bytes_20_2 = (run_dir / "stage20_run.log").read_bytes()
    # Every line should be a JSON object with sort_keys-stable
    # compact serialization. Round-trip and compare.
    for line in log_bytes_20_2.decode("utf-8").splitlines():
        parsed = json.loads(line)
        assert isinstance(parsed, dict)
        round_trip = json.dumps(
            parsed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        assert round_trip == line

    # Now do the same against a Stage 20.3 log.
    p3 = tmp_path / "synth3.log"
    write_stage20_3_run_log(p3, _events_a())
    for line in p3.read_text(encoding="utf-8").splitlines():
        parsed = json.loads(line)
        assert isinstance(parsed, dict)
        round_trip = json.dumps(
            parsed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        assert round_trip == line


# ---------------------------------------------------------------------------
# W23-W26: README
# ---------------------------------------------------------------------------


def test_w23_readme_contains_locked_phrases(tmp_path):
    p = tmp_path / "README.md"
    write_stage20_3_readme(
        p,
        stage20_run_id="rid_20_2",
        stage20_2_manifest_json_sha256="a" * 64,
        stage20_3_run_id="rid_20_3",
    )
    text = p.read_text(encoding="utf-8")
    assert "Registered 0 filters." in text
    assert "Evaluated 0 filters." in text
    assert "Mutated 0 candidates." in text
    assert "No live dispatch readiness was granted." in text
    # Both flag names must be present together with the word "false".
    assert "safe_for_live_dispatch" in text
    assert "live_dispatch_ready" in text
    # Specifically the sentence that ties both to "false".
    assert "are both false" in text


def test_w24_readme_substantive_line_count_le_30(tmp_path):
    p = tmp_path / "README.md"
    write_stage20_3_readme(
        p, stage20_run_id="rid_20_2",
        stage20_2_manifest_json_sha256="a" * 64,
        stage20_3_run_id="rid_20_3",
    )
    lines = p.read_text(encoding="utf-8").splitlines()
    substantive = [ln for ln in lines if ln.strip() != ""]
    assert len(substantive) <= 30


def test_w25_readme_lineage_substitution(tmp_path):
    p = tmp_path / "README.md"
    write_stage20_3_readme(
        p,
        stage20_run_id="my_20_2_id",
        stage20_2_manifest_json_sha256="z" * 64,
        stage20_3_run_id="my_20_3_id",
    )
    text = p.read_text(encoding="utf-8")
    assert "my_20_2_id" in text
    assert "z" * 64 in text
    assert "my_20_3_id" in text


def test_w26_readme_sha_stable_across_two_renders(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    common = dict(
        stage20_run_id="rid",
        stage20_2_manifest_json_sha256="a" * 64,
        stage20_3_run_id="r3",
    )
    sha_a = write_stage20_3_readme(a, **common)
    sha_b = write_stage20_3_readme(b, **common)
    assert sha_a == sha_b


# ---------------------------------------------------------------------------
# W27-W29: _compute_file_sha256 helper
# ---------------------------------------------------------------------------


def test_w27_compute_file_sha256_lowercase_hex(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world")
    sha = _compute_file_sha256(p)
    assert sha == sha.lower()
    assert all(c in "0123456789abcdef" for c in sha)


def test_w28_compute_file_sha256_matches_single_shot_small_file(tmp_path):
    p = tmp_path / "x.bin"
    payload = b"a" * 1024
    p.write_bytes(payload)
    assert _compute_file_sha256(p) == hashlib.sha256(payload).hexdigest()


def test_w29_compute_file_sha256_matches_single_shot_large_file(tmp_path):
    # > 128 KiB so chunked read takes effect.
    p = tmp_path / "big.bin"
    payload = (b"ab" * (96 * 1024))  # 192 KiB
    p.write_bytes(payload)
    assert _compute_file_sha256(p) == hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# T1-T2: token discipline
# ---------------------------------------------------------------------------


def test_t1_forbidden_token_absent_from_writers_module_source():
    src = pathlib.Path(
        filter_interface_writers.__file__
    ).resolve().read_bytes()
    assert _forbidden_fim_token().encode("utf-8") not in src


def test_t2_forbidden_token_absent_from_this_test_file():
    src = pathlib.Path(__file__).resolve().read_bytes()
    assert _forbidden_fim_token().encode("utf-8") not in src


# ---------------------------------------------------------------------------
# I1-I2: forbidden imports
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


def test_i1_writers_does_not_import_manifest_assembler():
    imports = _imported_modules(filter_interface_writers)
    assert "PHX2.stage20.manifest_assembler" not in imports


def test_i2_writers_does_not_import_artifact_writers():
    imports = _imported_modules(filter_interface_writers)
    assert "PHX2.stage20.artifact_writers" not in imports
