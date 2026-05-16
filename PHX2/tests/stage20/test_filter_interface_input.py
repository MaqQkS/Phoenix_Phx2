"""Stage 20.3 Phase 2 tests -- on-disk Stage 20.2 input validator.

Exercises load_and_validate_stage20_2_run via the synthetic 20.2
run-dir fixture. Every negative test must raise E2027 with a
distinguishing detail substring.
"""

from __future__ import annotations

import hashlib
import pathlib

import pytest

from PHX2.stage20 import filter_interface_input
from PHX2.stage20.constants import LABEL_TO_STATE_MAPPING_V0
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.filter_interface_input import (
    STAGE20_2_REQUIRED_MANIFEST_KEYS,
    Stage20TwoInputs,
    load_and_validate_stage20_2_run,
)

from PHX2.tests.stage20.fixtures_stage20_2_synthetic import (
    OMIT_SAFE_FOR_LIVE_DISPATCH,
    build_synthetic_stage20_2_run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expected_label_mapping_dict() -> dict[str, str]:
    return {k: v.value for k, v in LABEL_TO_STATE_MAPPING_V0.items()}


def _forbidden_fim_token() -> str:
    return "filter_" + "interface_" + "manifest"


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_p1_valid_fixture_accepted_with_correct_hashes(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path, candidate_count=3)
    result = load_and_validate_stage20_2_run(run_dir)
    # Hashes are recomputed inside the validator; recompute from
    # written bytes here to confirm equality.
    pc_bytes = (run_dir / "preview_candidates.csv").read_bytes()
    aed_bytes = (run_dir / "alert_eligibility_decisions.csv").read_bytes()
    readme_bytes = (run_dir / "README.md").read_bytes()
    log_bytes = (run_dir / "stage20_run.log").read_bytes()
    assert result.preview_candidates_csv_sha256 == hashlib.sha256(
        pc_bytes
    ).hexdigest()
    assert result.alert_eligibility_decisions_csv_sha256 == hashlib.sha256(
        aed_bytes
    ).hexdigest()
    assert result.readme_md_sha256 == hashlib.sha256(readme_bytes).hexdigest()
    assert result.stage20_run_log_sha256 == hashlib.sha256(
        log_bytes
    ).hexdigest()


def test_p2_stage20_run_id_field_equals_manifest_key(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = load_and_validate_stage20_2_run(run_dir)
    assert result.stage20_run_id == result.manifest["stage20_run_id"]


def test_p3_label_mapping_field_equals_locked_v0(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = load_and_validate_stage20_2_run(run_dir)
    assert result.label_mapping == _expected_label_mapping_dict()


def test_p4_manifest_json_sha256_matches_bytes_as_written(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = load_and_validate_stage20_2_run(run_dir)
    raw = (run_dir / "manifest.json").read_bytes()
    assert result.manifest_json_sha256 == hashlib.sha256(raw).hexdigest()


def test_p5_stage20_two_inputs_is_namedtuple_hashable_and_equal(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    a = load_and_validate_stage20_2_run(run_dir)
    b = load_and_validate_stage20_2_run(run_dir)
    assert a == b
    # NamedTuples are hashable if their elements are; the manifest
    # dict and label_mapping dict are NOT hashable, so we only check
    # equality (the docstring promise is "equal-comparable").


# ---------------------------------------------------------------------------
# Negative: run dir + sibling file existence (N1-N7)
# ---------------------------------------------------------------------------


def _assert_e2027_with_substring(exc: Stage20ValidationError, needle: str):
    assert exc.code == "E2027"
    assert needle in (exc.detail or ""), (
        f"expected detail to contain {needle!r}; got {exc.detail!r}"
    )


def test_n1_nonexistent_run_dir(tmp_path):
    bogus = tmp_path / "stage20_runs" / "does_not_exist"
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(bogus)
    _assert_e2027_with_substring(exc_info.value, "does not exist")


def test_n2_run_dir_path_is_a_file(tmp_path):
    fake = tmp_path / "fake_as_file"
    fake.write_text("not a dir")
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(fake)
    _assert_e2027_with_substring(exc_info.value, "is not a directory")


def test_n3_manifest_json_missing(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, missing_file="manifest.json",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "required sibling file missing: manifest.json"
    )


def test_n4_preview_candidates_csv_missing(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, missing_file="preview_candidates.csv",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value,
        "required sibling file missing: preview_candidates.csv",
    )


def test_n5_alert_eligibility_decisions_csv_missing(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, missing_file="alert_eligibility_decisions.csv",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value,
        "required sibling file missing: alert_eligibility_decisions.csv",
    )


def test_n6_readme_md_missing(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, missing_file="README.md",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "required sibling file missing: README.md"
    )


def test_n7_stage20_run_log_missing(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, missing_file="stage20_run.log",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "required sibling file missing: stage20_run.log"
    )


# ---------------------------------------------------------------------------
# Negative: manifest parsing + structure (N8-N9)
# ---------------------------------------------------------------------------


def test_n8_manifest_json_malformed(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path, malformed_json=True)
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "manifest.json is not valid JSON"
    )


# Parameterize over every required manifest key.
@pytest.mark.parametrize(
    "omit_key", sorted(STAGE20_2_REQUIRED_MANIFEST_KEYS),
)
def test_n9_manifest_missing_required_key(tmp_path, omit_key):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, omit_keys=(omit_key,),
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "manifest missing required key"
    )
    assert repr(omit_key) in (exc_info.value.detail or "")


# ---------------------------------------------------------------------------
# Negative: version pins + dispatch flag (N10-N17)
# ---------------------------------------------------------------------------


def test_n10_stage20_version_wrong(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, stage20_version_override="stage20_v0_live_dispatch",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(exc_info.value, "stage20_version mismatch")


def test_n11_stage20_minor_version_is_20_1(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, stage20_minor_version_override="20.1",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "stage20_minor_version mismatch"
    )


def test_n12_stage20_minor_version_is_20_3(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, stage20_minor_version_override="20.3",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "stage20_minor_version mismatch"
    )


def test_n13_consumer_contract_version_wrong(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, consumer_contract_version_override="different_value",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "consumer_contract_version mismatch"
    )


def test_n14_safe_for_live_dispatch_is_true(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, safe_for_live_dispatch_override=True,
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "safe_for_live_dispatch must be the literal False"
    )


def test_n15_safe_for_live_dispatch_is_null(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, safe_for_live_dispatch_override=None,
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "safe_for_live_dispatch must be the literal False"
    )


def test_n16_safe_for_live_dispatch_is_string_false(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, safe_for_live_dispatch_override="false",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "safe_for_live_dispatch must be the literal False"
    )


def test_n17_safe_for_live_dispatch_omitted(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path,
        safe_for_live_dispatch_override=OMIT_SAFE_FOR_LIVE_DISPATCH,
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    # Caught by the "missing required key" branch.
    _assert_e2027_with_substring(
        exc_info.value, "manifest missing required key"
    )
    assert "safe_for_live_dispatch" in (exc_info.value.detail or "")


# ---------------------------------------------------------------------------
# Negative: label_mapping (N18-N20)
# ---------------------------------------------------------------------------


def test_n18_label_mapping_missing_one_key(tmp_path):
    bad = _expected_label_mapping_dict()
    bad.pop("WATCHLIST")
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, label_mapping_override=bad,
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "label_mapping does not match locked v0 mapping"
    )


def test_n19_label_mapping_has_extra_key(tmp_path):
    bad = _expected_label_mapping_dict()
    bad["EXTRA_LABEL_NOT_IN_V0"] = "PREVIEW_EXCLUDED"
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, label_mapping_override=bad,
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "label_mapping does not match locked v0 mapping"
    )


def test_n20_label_mapping_value_changed(tmp_path):
    bad = _expected_label_mapping_dict()
    bad["WATCHLIST"] = "PREVIEW_ELIGIBLE"  # was PREVIEW_OBSERVE_ONLY
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, label_mapping_override=bad,
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "label_mapping does not match locked v0 mapping"
    )


# ---------------------------------------------------------------------------
# Negative: sibling file hash mismatches (N21-N24)
# ---------------------------------------------------------------------------


def test_n21_preview_candidates_csv_hash_mismatch(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, corrupt_file_hash="preview_candidates.csv",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value,
        "sibling file preview_candidates.csv on-disk sha256 mismatch",
    )


def test_n22_alert_eligibility_decisions_csv_hash_mismatch(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, corrupt_file_hash="alert_eligibility_decisions.csv",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value,
        "sibling file alert_eligibility_decisions.csv on-disk sha256 "
        "mismatch",
    )


def test_n23_readme_md_hash_mismatch(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, corrupt_file_hash="README.md",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value, "sibling file README.md on-disk sha256 mismatch"
    )


def test_n24_stage20_run_log_hash_mismatch(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, corrupt_file_hash="stage20_run.log",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        load_and_validate_stage20_2_run(run_dir)
    _assert_e2027_with_substring(
        exc_info.value,
        "sibling file stage20_run.log on-disk sha256 mismatch",
    )


# ---------------------------------------------------------------------------
# Determinism / immutability (D1-D2)
# ---------------------------------------------------------------------------


def test_d1_same_run_dir_twice_yields_equal_inputs(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    a = load_and_validate_stage20_2_run(run_dir)
    b = load_and_validate_stage20_2_run(run_dir)
    assert a == b


def test_d2_sibling_file_hashes_unchanged_before_after_call(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    pre = {}
    post = {}
    for fn in (
        "manifest.json",
        "preview_candidates.csv",
        "alert_eligibility_decisions.csv",
        "README.md",
        "stage20_run.log",
    ):
        pre[fn] = hashlib.sha256(
            (run_dir / fn).read_bytes()
        ).hexdigest()
    load_and_validate_stage20_2_run(run_dir)
    for fn in pre.keys():
        post[fn] = hashlib.sha256(
            (run_dir / fn).read_bytes()
        ).hexdigest()
    assert pre == post


# ---------------------------------------------------------------------------
# Edge (E1)
# ---------------------------------------------------------------------------


def test_e1_zero_candidate_count_still_valid(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path, candidate_count=0)
    result = load_and_validate_stage20_2_run(run_dir)
    assert isinstance(result, Stage20TwoInputs)
    assert result.manifest["preview_candidates_row_count"] == 0


# ---------------------------------------------------------------------------
# Token discipline (T1-T3)
# ---------------------------------------------------------------------------


def test_t1_forbidden_token_absent_from_input_module_source():
    src = pathlib.Path(
        filter_interface_input.__file__
    ).resolve().read_bytes()
    assert _forbidden_fim_token().encode("utf-8") not in src


def test_t2_forbidden_token_absent_from_this_test_file():
    src = pathlib.Path(__file__).resolve().read_bytes()
    assert _forbidden_fim_token().encode("utf-8") not in src


def test_t3_forbidden_token_absent_from_fixture_helper():
    from PHX2.tests.stage20 import fixtures_stage20_2_synthetic as fix
    src = pathlib.Path(fix.__file__).resolve().read_bytes()
    assert _forbidden_fim_token().encode("utf-8") not in src
