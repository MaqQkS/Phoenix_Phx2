"""Stage 20.3 Phase 1 tests -- constants, enums, and locked models.

Covers the empty filter interface surface declared in
``PHX2/stage20/filter_interface_models.py`` plus the additive
Stage 20.3 entries in ``PHX2/stage20/constants.py`` and
``PHX2/stage20/errors.py``.

Token discipline: this file MUST NOT contain the literal
substring "filter_" + "interface_" + "manifest". Tests T36/T37
verify by reading the file bytes and substring-scanning.
"""

from __future__ import annotations

import pathlib

import pytest

from PHX2.stage20 import constants as stage20_constants
from PHX2.stage20 import filter_interface_models
from PHX2.stage20.constants import (
    EligibilityErrorCode,
    ERROR_CODE_NAMES,
    FILTER_INTERFACE_REGISTRY_COLUMNS,
    FILTER_INTERFACE_RESULTS_COLUMNS,
    FILTER_INTERFACE_VERSION,
    FILTER_MODE_VALUES_V0,
    FILTER_REGISTRY_CONTRACT_VERSION,
    FILTER_RESULT_CONTRACT_VERSION,
    STAGE20_3_MINOR_VERSION,
    STAGE20_MINOR_VERSION,
)
from PHX2.stage20.errors import ERROR_MESSAGE_TEMPLATES, Stage20ValidationError
from PHX2.stage20.filter_interface_models import (
    FilterDefinition,
    FilterEvaluationRow,
    REGISTRY_V0,
    _validate_filter_definition,
    _validate_filter_evaluation_row,
    build_v0_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_definition(**overrides) -> FilterDefinition:
    base = dict(
        filter_id="f_synth_001",
        filter_name="synthetic_filter_for_tests",
        filter_version="v0.0.1",
        threshold_version="t0.0.1",
        mode="OBSERVE_ONLY",
        contract_version=FILTER_REGISTRY_CONTRACT_VERSION,
    )
    base.update(overrides)
    return FilterDefinition(**base)


def _make_valid_row(**overrides) -> FilterEvaluationRow:
    base = dict(
        candidate_id="cand_001",
        filter_id="f_synth_001",
        filter_name="synthetic_filter_for_tests",
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


def _forbidden_fim_token() -> str:
    """Reconstruct the forbidden filter-manifest token without
    embedding it. Built by concatenating three short fragments.
    """

    return "filter_" + "interface_" + "manifest"


# ---------------------------------------------------------------------------
# 1-8: constants and enum surface
# ---------------------------------------------------------------------------


def test_t01_filter_mode_values_v0_exact_tuple():
    assert FILTER_MODE_VALUES_V0 == ("DISABLED", "OBSERVE_ONLY")


def test_t02_filter_mode_values_v0_does_not_contain_blocking():
    assert "BLOCKING" not in FILTER_MODE_VALUES_V0


def test_t03_filter_mode_values_v0_does_not_contain_shadow():
    assert "SHADOW" not in FILTER_MODE_VALUES_V0


def test_t04_filter_interface_version_string_locked():
    assert FILTER_INTERFACE_VERSION == "filter_interface_v0_empty"


def test_t05_filter_registry_contract_version_locked():
    assert FILTER_REGISTRY_CONTRACT_VERSION == "filter_registry_contract_v0"


def test_t06_filter_result_contract_version_locked():
    assert FILTER_RESULT_CONTRACT_VERSION == "filter_result_contract_v0"


def test_t07_stage20_3_minor_version_locked():
    assert STAGE20_3_MINOR_VERSION == "20.3"


def test_t08_stage20_minor_version_unchanged_additive_only_proof():
    assert STAGE20_MINOR_VERSION == "20.2"


# ---------------------------------------------------------------------------
# 9-13: error-code surface
# ---------------------------------------------------------------------------


def test_t09_e2027_e2028_e2029_enum_members_exist():
    assert EligibilityErrorCode.E2027.value == "E2027"
    assert EligibilityErrorCode.E2028.value == "E2028"
    assert EligibilityErrorCode.E2029.value == "E2029"


def test_t10_snake_case_names_for_new_codes_locked():
    assert ERROR_CODE_NAMES["E2027"] == "stage20_2_input_contract_violation"
    assert ERROR_CODE_NAMES["E2028"] == "filter_registry_contract_violation"
    assert ERROR_CODE_NAMES["E2029"] == "filter_result_contract_violation"


def test_t11_error_message_templates_for_new_codes_locked():
    assert ERROR_MESSAGE_TEMPLATES["E2027"] == (
        "Stage 20.2 input contract violation"
    )
    assert ERROR_MESSAGE_TEMPLATES["E2028"] == (
        "Filter registry contract violation"
    )
    assert ERROR_MESSAGE_TEMPLATES["E2029"] == (
        "Filter result contract violation"
    )


def test_t12_existing_2013_era_names_unchanged_additive_only():
    assert ERROR_CODE_NAMES["E2012"] == "filter_interface_schema_violation"
    assert ERROR_CODE_NAMES["E2013"] == "filter_mode_not_observe_only_in_v0"
    assert ERROR_CODE_NAMES["E2014"] == "filter_ordering_index_collision"


def test_t13_banned_extra_ecode_not_in_eligibility_error_code():
    # Reconstruct the banned token at runtime so the source bytes
    # of this file never contain its literal form.
    banned = "E" + str(2026)
    members = {m.value for m in EligibilityErrorCode}
    assert banned not in members


# ---------------------------------------------------------------------------
# 14-17: column-order constants
# ---------------------------------------------------------------------------


def test_t14_registry_columns_locked_six_tuple_in_order():
    assert FILTER_INTERFACE_REGISTRY_COLUMNS == (
        "filter_id",
        "filter_name",
        "filter_version",
        "threshold_version",
        "mode",
        "contract_version",
    )


def test_t15_results_columns_locked_ten_tuple_in_order():
    assert FILTER_INTERFACE_RESULTS_COLUMNS == (
        "candidate_id",
        "filter_id",
        "filter_name",
        "filter_version",
        "threshold_version",
        "mode",
        "evaluation_status",
        "observation_label",
        "observation_detail_json",
        "contract_version",
    )


def test_t16_registry_columns_match_definition_fields_elementwise():
    assert FILTER_INTERFACE_REGISTRY_COLUMNS == FilterDefinition._fields


def test_t17_results_columns_match_row_fields_elementwise():
    assert FILTER_INTERFACE_RESULTS_COLUMNS == FilterEvaluationRow._fields


# ---------------------------------------------------------------------------
# 18-26: FilterDefinition shape and validation
# ---------------------------------------------------------------------------


def test_t18_filter_definition_fields_exact_order():
    assert FilterDefinition._fields == (
        "filter_id",
        "filter_name",
        "filter_version",
        "threshold_version",
        "mode",
        "contract_version",
    )


def test_t19_filter_definition_has_no_registered_at_utc_attribute():
    assert "registered_at_utc" not in FilterDefinition._fields


def test_t20_valid_definition_passes_validator_silently():
    _validate_filter_definition(_make_valid_definition())


def test_t21_definition_rejects_blocking_mode_with_e2028():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_definition(_make_valid_definition(mode="BLOCKING"))
    assert exc_info.value.code == "E2028"


def test_t22_definition_rejects_shadow_mode_with_e2028():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_definition(_make_valid_definition(mode="SHADOW"))
    assert exc_info.value.code == "E2028"


def test_t23_definition_rejects_empty_mode_with_e2028():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_definition(_make_valid_definition(mode=""))
    assert exc_info.value.code == "E2028"


def test_t24_definition_rejects_lowercase_observe_only_with_e2028():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_definition(
            _make_valid_definition(mode="observe_only")
        )
    assert exc_info.value.code == "E2028"


def test_t25_definition_rejects_contract_version_mismatch_with_e2028():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_definition(
            _make_valid_definition(contract_version="wrong_contract")
        )
    assert exc_info.value.code == "E2028"


def test_t26_definition_rejects_empty_filter_id_with_e2028():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_definition(_make_valid_definition(filter_id=""))
    assert exc_info.value.code == "E2028"


# ---------------------------------------------------------------------------
# 27-32: FilterEvaluationRow shape and validation
# ---------------------------------------------------------------------------


def test_t27_evaluation_row_fields_exact_order():
    assert FilterEvaluationRow._fields == (
        "candidate_id",
        "filter_id",
        "filter_name",
        "filter_version",
        "threshold_version",
        "mode",
        "evaluation_status",
        "observation_label",
        "observation_detail_json",
        "contract_version",
    )


def test_t28_valid_row_passes_validator_silently():
    _validate_filter_evaluation_row(_make_valid_row())


def test_t29_row_rejects_blocking_mode_with_e2029():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_evaluation_row(_make_valid_row(mode="BLOCKING"))
    assert exc_info.value.code == "E2029"


def test_t30_row_rejects_contract_version_mismatch_with_e2029():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_evaluation_row(
            _make_valid_row(contract_version="wrong_contract")
        )
    assert exc_info.value.code == "E2029"


def test_t31_row_rejects_observation_detail_not_json():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_evaluation_row(
            _make_valid_row(observation_detail_json="not a json object")
        )
    assert exc_info.value.code == "E2029"


def test_t32_row_rejects_observation_detail_json_list():
    with pytest.raises(Stage20ValidationError) as exc_info:
        _validate_filter_evaluation_row(
            _make_valid_row(observation_detail_json="[1, 2, 3]")
        )
    assert exc_info.value.code == "E2029"


# ---------------------------------------------------------------------------
# 33-35: registry surface
# ---------------------------------------------------------------------------


def test_t33_registry_v0_is_empty_tuple():
    assert REGISTRY_V0 == ()


def test_t34_build_v0_registry_returns_empty_tuple():
    assert build_v0_registry() == ()


def test_t35_build_v0_registry_returns_same_identity_across_calls():
    a = build_v0_registry()
    b = build_v0_registry()
    assert a is b


# ---------------------------------------------------------------------------
# 36-37: token discipline (D2)
# ---------------------------------------------------------------------------


def _module_file(module) -> pathlib.Path:
    return pathlib.Path(module.__file__).resolve()


def test_t36_forbidden_token_absent_from_models_module_source():
    token = _forbidden_fim_token()
    src = _module_file(filter_interface_models).read_bytes()
    assert token.encode("utf-8") not in src


def test_t37_forbidden_token_absent_from_this_test_file():
    token = _forbidden_fim_token()
    this_path = pathlib.Path(__file__).resolve()
    src = this_path.read_bytes()
    assert token.encode("utf-8") not in src


# ---------------------------------------------------------------------------
# 38-39: dormant scaffold isolation (INFO-2) + boundary checks
# ---------------------------------------------------------------------------


def _imported_modules(module) -> set[str]:
    """Return the set of dotted module names imported by ``module``.

    Static AST scan; catches both ``import X`` and ``from X import Y``.
    """

    import ast

    src = _module_file(module).read_text(encoding="utf-8")
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


def test_t38_models_module_does_not_import_filter_result_scaffold():
    imports = _imported_modules(filter_interface_models)
    assert "PHX2.stage20.models.filter_result" not in imports
    # Also reject any shorter prefix the model could be imported via.
    assert "PHX2.stage20.models" not in imports


def test_t39_models_module_does_not_import_phx2_stage17_18_19():
    imports = _imported_modules(filter_interface_models)
    forbidden_prefixes = ("PHX2.stage17", "PHX2.stage18", "PHX2.stage19")
    for imp in imports:
        for prefix in forbidden_prefixes:
            assert not imp.startswith(prefix), (
                f"forbidden upstream import {imp!r}"
            )


# ---------------------------------------------------------------------------
# Bonus: prove the constants module is the legitimate label-mapping site
# ---------------------------------------------------------------------------


def test_constants_module_path_resolvable():
    # Sanity: the additive-only edits in constants.py are reachable.
    assert hasattr(stage20_constants, "FILTER_INTERFACE_VERSION")
    assert hasattr(stage20_constants, "STAGE20_3_MINOR_VERSION")
