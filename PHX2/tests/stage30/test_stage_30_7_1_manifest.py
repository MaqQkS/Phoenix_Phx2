"""Stage 30.7.1 manifest pin tests.

Pins the Stage 30.7.1 manifest constants (minor version, schema /
projection versions, default market-context unit, basenames + module
paths + inventory, scanned production basenames, test basenames,
stdlib + PHX2 import allowlists, the mirrored ATH status / source-
status / unit / basis / reason closed-set tuples), asserts the
production + test files exist, cross-checks the mirrored closed sets +
versions against the Stage 30.7.1 models module, asserts the manifest
edit is purely additive (the Stage 30.7.0 constants survive) and is
still constants-only, and asserts the manifest exports the surface.

Doc / constants only. No live call, no env read, no provider, no
Discord.
"""

from __future__ import annotations

import ast
from pathlib import Path

import PHX2.stage30.stage30_7_manifest as M
from PHX2.stage30.stage30_7_manifest import (
    STAGE30_7_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_7_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_7_1_ATH_BASIS_VALUES,
    STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME,
    STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_MODULE,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION,
    STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION,
    STAGE30_7_1_ATH_REASON_VALUES,
    STAGE30_7_1_ATH_SOURCE_STATUS_VALUES,
    STAGE30_7_1_ATH_STATUS_VALUES,
    STAGE30_7_1_ATH_UNIT_VALUES,
    STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
    STAGE30_7_1_MINOR_VERSION,
    STAGE30_7_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_7_1_TEST_BASENAMES,
    STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_0,
    STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_1,
    STAGE30_7_MANIFEST_BASENAME,
    STAGE30_7_MINOR_VERSION,
    STAGE30_7_SPEC_BASENAME,
)
from PHX2.stage30.stage30_7_ath_context_models import (
    ATH_BASIS_VALUES,
    ATH_REASON_VALUES,
    ATH_SOURCE_STATUS_VALUES,
    ATH_STATUS_VALUES,
    ATH_UNIT_VALUES,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION as MODELS_PROJ_VERSION,
    STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT as MODELS_DEFAULT_UNIT,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Versions + schema / projection version + default unit
# ---------------------------------------------------------------------------


def test_minor_versions_pinned() -> None:
    assert STAGE30_7_MINOR_VERSION == "30.7"
    assert STAGE30_7_1_MINOR_VERSION == "30.7.1"


def test_versions_and_default_unit_match_models() -> None:
    assert STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION == (
        "stage30_7_1_v0_ath_context"
    )
    assert STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION == MODELS_SCHEMA_VERSION
    assert STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION == (
        "stage30_7_ath_context_projection_v0"
    )
    assert STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION == MODELS_PROJ_VERSION
    assert STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT == "USD"
    assert STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT == MODELS_DEFAULT_UNIT


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_production_basenames_pinned_and_exist() -> None:
    assert STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME == (
        "stage30_7_ath_context_models.py"
    )
    assert STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME == (
        "stage30_7_ath_context_projection.py"
    )
    for basename in STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_1:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.7.1 requires {basename}"
        )


def test_module_paths_pinned() -> None:
    assert STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE == (
        "PHX2.stage30.stage30_7_ath_context_models"
    )
    assert STAGE30_7_1_ATH_CONTEXT_PROJECTION_MODULE == (
        "PHX2.stage30.stage30_7_ath_context_projection"
    )


def test_allowed_stage30_basenames_is_the_two_modules() -> None:
    assert STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_1 == (
        STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME,
        STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME,
    )


def test_scanned_production_basenames_are_the_two_modules() -> None:
    assert STAGE30_7_1_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME,
        STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME,
    )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_7_1_TEST_BASENAMES == (
        "test_stage_30_7_1_ath_context_models.py",
        "test_stage_30_7_1_ath_context_projection.py",
        "test_stage_30_7_1_boundaries.py",
        "test_stage_30_7_1_manifest.py",
    )
    for basename in STAGE30_7_1_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.7.1 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_7_1_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
        "math",
        "re",
    )


def test_phx2_import_allowlist_is_only_the_models_sibling() -> None:
    assert STAGE30_7_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
    )
    for module in STAGE30_7_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_7_")


# ---------------------------------------------------------------------------
# 4. Mirrored closed sets match the models module
# ---------------------------------------------------------------------------


def test_status_values_mirror_models() -> None:
    assert STAGE30_7_1_ATH_STATUS_VALUES == (
        "ATH_KNOWN",
        "ATH_UNVERIFIED",
        "ATH_UNKNOWN",
    )
    assert STAGE30_7_1_ATH_STATUS_VALUES == ATH_STATUS_VALUES


def test_source_status_values_mirror_models() -> None:
    assert STAGE30_7_1_ATH_SOURCE_STATUS_VALUES == (
        "PRESENT",
        "UNAVAILABLE",
        "ERROR",
        "STALE",
        "CONFLICTING",
    )
    assert (
        STAGE30_7_1_ATH_SOURCE_STATUS_VALUES == ATH_SOURCE_STATUS_VALUES
    )


def test_unit_values_mirror_models() -> None:
    assert STAGE30_7_1_ATH_UNIT_VALUES == ("USD", "SOL", "UNKNOWN")
    assert STAGE30_7_1_ATH_UNIT_VALUES == ATH_UNIT_VALUES


def test_basis_values_mirror_models() -> None:
    assert STAGE30_7_1_ATH_BASIS_VALUES == (
        "ATH_MARKET_CAP_OBSERVED",
        "ATH_PRICE_DERIVED",
        "ATH_BASIS_NONE",
    )
    assert STAGE30_7_1_ATH_BASIS_VALUES == ATH_BASIS_VALUES


def test_reason_values_mirror_models() -> None:
    assert len(STAGE30_7_1_ATH_REASON_VALUES) == 14
    assert STAGE30_7_1_ATH_REASON_VALUES == ATH_REASON_VALUES


# ---------------------------------------------------------------------------
# 5. Manifest edit is additive + still constants-only
# ---------------------------------------------------------------------------


def test_stage30_7_0_inventory_constants_survive() -> None:
    # The Stage 30.7.1 manifest edit is purely additive: the Stage
    # 30.7.0 constants the 30.7.0 pin test imports must remain, and the
    # 30.7.0 allowed-basenames constant must be UNCHANGED.
    assert STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_0 == (
        STAGE30_7_SPEC_BASENAME,
        STAGE30_7_MANIFEST_BASENAME,
    )
    for name in (
        "STAGE30_7_MINOR_VERSION",
        "STAGE30_7_0_MINOR_VERSION",
        "STAGE30_7_SPEC_BASENAME",
        "STAGE30_7_MANIFEST_BASENAME",
        "STAGE30_7_SUBSTAGE_SEQUENCE",
        "STAGE30_7_ATH_STATUS_VALUES",
        "STAGE30_7_FORBIDDEN_RUNTIME_IMPORTS",
        "STAGE30_7_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__, f"30.7.0 surface {name!r} must survive"


def test_manifest_still_constants_only() -> None:
    """AST proof that the additive 30.7.1 edit kept the manifest
    constants-only: no def / class / Call anywhere, only
    ``__future__`` + ``typing`` imports.
    """
    manifest_path = STAGE30_ROOT / STAGE30_7_MANIFEST_BASENAME
    tree = ast.parse(manifest_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), "Stage 30.7 manifest must stay constants-only (no def/class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.7 manifest must stay constants-only (no Call)"
        )
    allowed_import_roots = {"__future__", "typing"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in allowed_import_roots


# ---------------------------------------------------------------------------
# 6. Manifest __all__ exports the Stage 30.7.1 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_surface() -> None:
    for name in (
        "STAGE30_7_1_MINOR_VERSION",
        "STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION",
        "STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION",
        "STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT",
        "STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME",
        "STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME",
        "STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE",
        "STAGE30_7_1_ATH_CONTEXT_PROJECTION_MODULE",
        "STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_1",
        "STAGE30_7_1_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_7_1_TEST_BASENAMES",
        "STAGE30_7_1_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_7_1_ALLOWED_PHX2_IMPORTS",
        "STAGE30_7_1_ATH_STATUS_VALUES",
        "STAGE30_7_1_ATH_SOURCE_STATUS_VALUES",
        "STAGE30_7_1_ATH_UNIT_VALUES",
        "STAGE30_7_1_ATH_BASIS_VALUES",
        "STAGE30_7_1_ATH_REASON_VALUES",
    ):
        assert name in M.__all__, (
            f"manifest __all__ must export {name!r}"
        )
