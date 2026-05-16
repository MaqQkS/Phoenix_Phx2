"""Stage 20.3 Phase 3 tests -- manifest assembly + run-id derivation.

Pure-function coverage only: no file I/O, no clock, no runner. The
runner-level wiring lands in Phase 5.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from PHX2.stage20 import stage20_3_manifest
from PHX2.stage20.constants import (
    CONSUMER_CONTRACT_VERSION,
    FILTER_INTERFACE_VERSION,
    FILTER_REGISTRY_CONTRACT_VERSION,
    FILTER_RESULT_CONTRACT_VERSION,
    LABEL_TO_STATE_MAPPING_V0,
    STAGE20_MINOR_VERSION,
    STAGE20_VERSION,
)
from PHX2.stage20.filter_interface_input import Stage20TwoInputs
from PHX2.stage20.stage20_3_manifest import (
    STAGE20_3_MANIFEST_ARTIFACT_FILENAME,
    V0_NOTE,
    assemble_stage20_3_manifest,
    derive_stage20_3_run_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expected_label_mapping() -> dict[str, str]:
    return {k: v.value for k, v in LABEL_TO_STATE_MAPPING_V0.items()}


def _make_synthetic_inputs() -> Stage20TwoInputs:
    return Stage20TwoInputs(
        stage20_2_run_dir=pathlib.Path("synthetic/path"),
        stage20_run_id="synth_stage20_run_id_001",
        manifest={"synthetic": True},
        manifest_json_sha256="a" * 64,
        preview_candidates_csv_sha256="b" * 64,
        alert_eligibility_decisions_csv_sha256="c" * 64,
        readme_md_sha256="d" * 64,
        stage20_run_log_sha256="e" * 64,
        label_mapping=_expected_label_mapping(),
    )


# Locked expected key set (sorted) used by M1.
_EXPECTED_MANIFEST_KEYS_SORTED = sorted([
    "stage20_version",
    "stage20_3_minor_version",
    "stage20_3_run_id",
    "generated_at_utc",
    "filter_interface_version",
    "filter_registry_contract_version",
    "filter_result_contract_version",
    "filter_mode_enum_v0",
    "interface_initialized",
    "registered_filter_count",
    "evaluated_filter_count",
    "candidate_mutation_count",
    "blocking_filter_count",
    "enforcement_enabled",
    "v0_interface_intentionally_empty",
    "safe_for_live_dispatch",
    "live_dispatch_ready",
    "stage20_2_lineage",
    "stage20_3_manifest_artifact_filename",
    "filter_interface_registry_csv_sha256",
    "filter_interface_results_csv_sha256",
    "stage20_3_run_log_sha256",
    "readme_md_sha256",
    "errors",
    "warnings",
    "notes",
])


_EXPECTED_LINEAGE_KEYS_SORTED = sorted([
    "stage20_run_id",
    "stage20_minor_version",
    "stage20_version",
    "consumer_contract_version",
    "manifest_json_sha256",
    "preview_candidates_csv_sha256",
    "alert_eligibility_decisions_csv_sha256",
    "readme_md_sha256",
    "stage20_run_log_sha256",
    "safe_for_live_dispatch",
    "label_mapping",
])


def _forbidden_fim_token() -> str:
    return "filter_" + "interface_" + "manifest"


def _assemble(**overrides) -> dict:
    base = dict(
        inputs=_make_synthetic_inputs(),
        stage20_3_run_id="0123456789abcdef",
        generated_at_utc="2026-05-15T12:34:56Z",
        filter_interface_registry_csv_sha256="r" * 64,
        filter_interface_results_csv_sha256="s" * 64,
        stage20_3_run_log_sha256="l" * 64,
        readme_md_sha256="m" * 64,
    )
    base.update(overrides)
    return assemble_stage20_3_manifest(**base)


# ---------------------------------------------------------------------------
# R1-R5: derive_stage20_3_run_id
# ---------------------------------------------------------------------------


def test_r1_run_id_deterministic_across_repeated_calls():
    a = derive_stage20_3_run_id("stage20_a", "x" * 64)
    b = derive_stage20_3_run_id("stage20_a", "x" * 64)
    assert a == b


def test_r2_run_id_length_and_lowercase_hex():
    rid = derive_stage20_3_run_id("stage20_a", "x" * 64)
    assert len(rid) == 16
    assert all(c in "0123456789abcdef" for c in rid)


def test_r3_run_id_differs_when_stage20_run_id_differs():
    a = derive_stage20_3_run_id("stage20_a", "x" * 64)
    b = derive_stage20_3_run_id("stage20_b", "x" * 64)
    assert a != b


def test_r4_run_id_differs_when_manifest_sha_differs():
    a = derive_stage20_3_run_id("stage20_a", "x" * 64)
    b = derive_stage20_3_run_id("stage20_a", "y" * 64)
    assert a != b


def test_r5_run_id_output_bytes_identical_for_identical_inputs():
    a = derive_stage20_3_run_id("stage20_a", "x" * 64)
    b = derive_stage20_3_run_id("stage20_a", "x" * 64)
    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(
        b.encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# M1-M19: assemble_stage20_3_manifest
# ---------------------------------------------------------------------------


def test_m1_top_level_key_set_matches_locked_set():
    manifest = _assemble()
    assert sorted(manifest.keys()) == _EXPECTED_MANIFEST_KEYS_SORTED


def test_m2_stage20_version_string_locked():
    manifest = _assemble()
    assert manifest["stage20_version"] == "stage20_v0_observe_only"


def test_m3_stage20_3_minor_version_string_locked():
    manifest = _assemble()
    assert manifest["stage20_3_minor_version"] == "20.3"


def test_m4_safe_for_live_dispatch_is_python_false_serializes_false():
    manifest = _assemble()
    assert manifest["safe_for_live_dispatch"] is False
    rendered = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    )
    # Confirm JSON `false` literal appears for this key.
    assert '"safe_for_live_dispatch":false' in rendered


def test_m5_live_dispatch_ready_is_python_false():
    manifest = _assemble()
    assert manifest["live_dispatch_ready"] is False


def test_m6_zero_counter_fields_are_integer_zero():
    manifest = _assemble()
    for key in (
        "registered_filter_count",
        "evaluated_filter_count",
        "candidate_mutation_count",
        "blocking_filter_count",
    ):
        assert isinstance(manifest[key], int)
        assert manifest[key] == 0


def test_m7_enforcement_enabled_is_python_false():
    manifest = _assemble()
    assert manifest["enforcement_enabled"] is False


def test_m8_interface_initialized_is_python_true():
    manifest = _assemble()
    assert manifest["interface_initialized"] is True


def test_m9_v0_interface_intentionally_empty_is_python_true():
    manifest = _assemble()
    assert manifest["v0_interface_intentionally_empty"] is True


def test_m10_filter_mode_enum_v0_locked_list():
    manifest = _assemble()
    assert manifest["filter_mode_enum_v0"] == ["DISABLED", "OBSERVE_ONLY"]


def test_m11_lineage_has_all_eleven_expected_keys():
    manifest = _assemble()
    assert sorted(manifest["stage20_2_lineage"].keys()) == (
        _EXPECTED_LINEAGE_KEYS_SORTED
    )


def test_m12_lineage_label_mapping_equals_locked_v0():
    manifest = _assemble()
    assert manifest["stage20_2_lineage"]["label_mapping"] == (
        _expected_label_mapping()
    )


def test_m13_lineage_safe_for_live_dispatch_is_false():
    manifest = _assemble()
    assert manifest["stage20_2_lineage"]["safe_for_live_dispatch"] is False


def test_m14_manifest_artifact_filename_locked():
    manifest = _assemble()
    assert manifest["stage20_3_manifest_artifact_filename"] == (
        "stage20_3_manifest.json"
    )


def test_m15_notes_list_exactly_v0_note():
    manifest = _assemble()
    assert manifest["notes"] == [V0_NOTE]


def test_m16_errors_and_warnings_are_empty_lists():
    manifest = _assemble()
    assert manifest["errors"] == []
    assert manifest["warnings"] == []


def test_m17_two_calls_serialize_byte_identically():
    a = _assemble()
    b = _assemble()
    ba = json.dumps(
        a, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8") + b"\n"
    bb = json.dumps(
        b, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8") + b"\n"
    assert ba == bb


def test_m18_serialized_json_ends_with_one_newline_no_carriage_return():
    manifest = _assemble()
    rendered = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"
    assert rendered.endswith("\n")
    assert not rendered.endswith("\r\n")
    assert "\r" not in rendered


def test_m19_round_trip_through_json_loads_then_dumps_is_byte_identical():
    manifest = _assemble()
    first = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    )
    reparsed = json.loads(first)
    second = json.dumps(
        reparsed, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    )
    assert first == second


# Bonus: stage20_2_lineage carries the copied/reverified hashes verbatim.


def test_lineage_carries_copied_input_hashes_verbatim():
    inputs = _make_synthetic_inputs()
    manifest = _assemble(inputs=inputs)
    lin = manifest["stage20_2_lineage"]
    assert lin["manifest_json_sha256"] == inputs.manifest_json_sha256
    assert lin["preview_candidates_csv_sha256"] == (
        inputs.preview_candidates_csv_sha256
    )
    assert lin["alert_eligibility_decisions_csv_sha256"] == (
        inputs.alert_eligibility_decisions_csv_sha256
    )
    assert lin["readme_md_sha256"] == inputs.readme_md_sha256
    assert lin["stage20_run_log_sha256"] == inputs.stage20_run_log_sha256
    assert lin["stage20_run_id"] == inputs.stage20_run_id
    assert lin["stage20_minor_version"] == STAGE20_MINOR_VERSION
    assert lin["stage20_version"] == STAGE20_VERSION
    assert lin["consumer_contract_version"] == CONSUMER_CONTRACT_VERSION


# ---------------------------------------------------------------------------
# T1-T3: Token discipline
# ---------------------------------------------------------------------------


def test_t1_forbidden_token_absent_from_manifest_module_source():
    src = pathlib.Path(
        stage20_3_manifest.__file__
    ).resolve().read_bytes()
    assert _forbidden_fim_token().encode("utf-8") not in src


def test_t2_forbidden_token_absent_from_this_test_file():
    src = pathlib.Path(__file__).resolve().read_bytes()
    assert _forbidden_fim_token().encode("utf-8") not in src


def test_t3_dropped_pascalcase_class_name_absent():
    # The optional NamedTuple was dropped per D2; ensure no
    # PascalCase residue. The token to forbid is reconstructed at
    # runtime so this test's source bytes never embed it.
    pascal = "Filter" + "Interface" + "Manifest"
    for path in (
        pathlib.Path(stage20_3_manifest.__file__).resolve(),
        pathlib.Path(__file__).resolve(),
    ):
        assert pascal.encode("utf-8") not in path.read_bytes(), (
            f"unexpected PascalCase residue in {path}"
        )


# Helper: every Stage 20.3 manifest field that should be exactly the
# Python literal False (not 0, not "", not None).


@pytest.mark.parametrize(
    "key",
    ["safe_for_live_dispatch", "live_dispatch_ready", "enforcement_enabled"],
)
def test_explicit_false_fields_are_literal_python_false(key):
    manifest = _assemble()
    assert manifest[key] is False
    # Also confirm none of these is just truthy-coerced.
    assert manifest[key] is not 0  # noqa: F632  (deliberate identity)


@pytest.mark.parametrize(
    "key",
    [
        "interface_initialized",
        "v0_interface_intentionally_empty",
    ],
)
def test_explicit_true_fields_are_literal_python_true(key):
    manifest = _assemble()
    assert manifest[key] is True
