"""Stage 30.6.1 manifest pin tests.

Pins the Stage 30.6.1 manifest constants (minor version, schema /
policy versions, basenames + module paths + inventory, scanned
production basenames, test basenames, stdlib + PHX2 import allowlists,
the mirrored status / action closed-set tuples, the float default
thresholds), asserts the production + test files exist, cross-checks
the mirrored closed sets / defaults against the Stage 30.6.1 models
module, and asserts the manifest exports the surface.

Doc / constants only. No live call, no env read, no actual-disk read.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_6_manifest as M
from PHX2.stage30.stage30_6_manifest import (
    STAGE30_6_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_6_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_6_1_DEFAULT_HARD_STOP_USED_PCT,
    STAGE30_6_1_DEFAULT_SOFT_ALARM_USED_PCT,
    STAGE30_6_1_MINOR_VERSION,
    STAGE30_6_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_6_1_STORAGE_BUDGET_ACTION_VALUES,
    STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_BASENAME,
    STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_MODULE,
    STAGE30_6_1_STORAGE_BUDGET_MODELS_BASENAME,
    STAGE30_6_1_STORAGE_BUDGET_MODELS_MODULE,
    STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION,
    STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION,
    STAGE30_6_1_STORAGE_BUDGET_STATUS_VALUES,
    STAGE30_6_1_TEST_BASENAMES,
    STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_1,
    STAGE30_6_MINOR_VERSION,
)
from PHX2.stage30.stage30_6_storage_budget_models import (
    STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION as MODELS_POLICY_VERSION,
    STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STORAGE_BUDGET_ACTION_VALUES,
    STORAGE_BUDGET_DEFAULT_HARD_STOP_USED_PCT,
    STORAGE_BUDGET_DEFAULT_SOFT_ALARM_USED_PCT,
    STORAGE_BUDGET_STATUS_VALUES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Versions + schema / policy version
# ---------------------------------------------------------------------------


def test_minor_versions_pinned() -> None:
    assert STAGE30_6_MINOR_VERSION == "30.6"
    assert STAGE30_6_1_MINOR_VERSION == "30.6.1"


def test_schema_and_policy_versions_match_models() -> None:
    assert STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION == (
        "stage30_6_1_v0_storage_budget"
    )
    assert STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION == (
        MODELS_SCHEMA_VERSION
    )
    assert STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION == (
        "stage30_6_storage_budget_policy_v0"
    )
    assert STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION == (
        MODELS_POLICY_VERSION
    )


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_production_basenames_pinned_and_exist() -> None:
    assert STAGE30_6_1_STORAGE_BUDGET_MODELS_BASENAME == (
        "stage30_6_storage_budget_models.py"
    )
    assert STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_BASENAME == (
        "stage30_6_storage_budget_evaluator.py"
    )
    for basename in STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_1:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.6.1 requires {basename}"
        )


def test_module_paths_pinned() -> None:
    assert STAGE30_6_1_STORAGE_BUDGET_MODELS_MODULE == (
        "PHX2.stage30.stage30_6_storage_budget_models"
    )
    assert STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_MODULE == (
        "PHX2.stage30.stage30_6_storage_budget_evaluator"
    )


def test_allowed_stage30_basenames_is_the_two_modules() -> None:
    assert STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_1 == (
        STAGE30_6_1_STORAGE_BUDGET_MODELS_BASENAME,
        STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_BASENAME,
    )


def test_scanned_production_basenames_are_the_two_modules() -> None:
    assert STAGE30_6_1_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_6_1_STORAGE_BUDGET_MODELS_BASENAME,
        STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_BASENAME,
    )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_6_1_TEST_BASENAMES == (
        "test_stage_30_6_1_storage_budget_models.py",
        "test_stage_30_6_1_storage_budget_evaluator.py",
        "test_stage_30_6_1_boundaries.py",
        "test_stage_30_6_1_manifest.py",
    )
    for basename in STAGE30_6_1_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.6.1 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_6_1_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "math",
    )


def test_phx2_import_allowlist_is_only_the_models_sibling() -> None:
    assert STAGE30_6_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_6_1_STORAGE_BUDGET_MODELS_MODULE,
    )
    for module in STAGE30_6_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_6_")


# ---------------------------------------------------------------------------
# 4. Mirrored closed sets + default thresholds match the models module
# ---------------------------------------------------------------------------


def test_status_values_mirror_models() -> None:
    assert STAGE30_6_1_STORAGE_BUDGET_STATUS_VALUES == (
        "STORAGE_BUDGET_OK",
        "STORAGE_BUDGET_SOFT_ALARM",
        "STORAGE_BUDGET_HARD_STOP",
        "STORAGE_BUDGET_INVALID_INPUT",
    )
    assert (
        STAGE30_6_1_STORAGE_BUDGET_STATUS_VALUES
        == STORAGE_BUDGET_STATUS_VALUES
    )


def test_action_values_mirror_models() -> None:
    assert STAGE30_6_1_STORAGE_BUDGET_ACTION_VALUES == (
        "ALLOW_WRITES",
        "ALLOW_WRITES_WITH_WARNING",
        "REFUSE_NEW_WRITES",
        "INVALID_INPUT_REFUSE_WRITES",
    )
    assert (
        STAGE30_6_1_STORAGE_BUDGET_ACTION_VALUES
        == STORAGE_BUDGET_ACTION_VALUES
    )


def test_default_thresholds_mirror_models() -> None:
    assert STAGE30_6_1_DEFAULT_SOFT_ALARM_USED_PCT == 65.0
    assert STAGE30_6_1_DEFAULT_HARD_STOP_USED_PCT == 90.0
    assert (
        STAGE30_6_1_DEFAULT_SOFT_ALARM_USED_PCT
        == STORAGE_BUDGET_DEFAULT_SOFT_ALARM_USED_PCT
    )
    assert (
        STAGE30_6_1_DEFAULT_HARD_STOP_USED_PCT
        == STORAGE_BUDGET_DEFAULT_HARD_STOP_USED_PCT
    )


def test_default_thresholds_align_with_stage30_6_integer_guardrails() -> (
    None
):
    # The Stage 30.6.0 manifest pins the integer 65 / 90 guardrails;
    # the Stage 30.6.1 float defaults must match them numerically.
    assert (
        STAGE30_6_1_DEFAULT_SOFT_ALARM_USED_PCT
        == float(M.STAGE30_6_DISK_SOFT_ALARM_PERCENT)
    )
    assert (
        STAGE30_6_1_DEFAULT_HARD_STOP_USED_PCT
        == float(M.STAGE30_6_DISK_HARD_STOP_PERCENT)
    )


# ---------------------------------------------------------------------------
# 5. Manifest __all__ exports the Stage 30.6.1 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_surface() -> None:
    for name in (
        "STAGE30_6_1_MINOR_VERSION",
        "STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION",
        "STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION",
        "STAGE30_6_1_STORAGE_BUDGET_MODELS_BASENAME",
        "STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_BASENAME",
        "STAGE30_6_1_STORAGE_BUDGET_MODELS_MODULE",
        "STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_MODULE",
        "STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_1",
        "STAGE30_6_1_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_6_1_TEST_BASENAMES",
        "STAGE30_6_1_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_6_1_ALLOWED_PHX2_IMPORTS",
        "STAGE30_6_1_STORAGE_BUDGET_STATUS_VALUES",
        "STAGE30_6_1_STORAGE_BUDGET_ACTION_VALUES",
        "STAGE30_6_1_DEFAULT_SOFT_ALARM_USED_PCT",
        "STAGE30_6_1_DEFAULT_HARD_STOP_USED_PCT",
    ):
        assert name in M.__all__, (
            f"manifest __all__ must export {name!r}"
        )


def test_stage30_6_0_inventory_constants_still_present() -> None:
    # The Stage 30.6.1 manifest edit is purely additive: the Stage
    # 30.6.0 constants the 30.6.0 pin test imports must remain.
    for name in (
        "STAGE30_6_0_MINOR_VERSION",
        "STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_0",
        "STAGE30_6_SUBSTAGE_SEQUENCE",
        "STAGE30_6_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__
