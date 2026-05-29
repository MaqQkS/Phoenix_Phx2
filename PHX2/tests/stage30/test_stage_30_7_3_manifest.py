"""Stage 30.7.3 manifest pin tests.

Pins the Stage 30.7.3 manifest constants (minor version, sanitized ATH
bridge basename + module path, inventory + scanned basenames, test
basenames, stdlib + PHX2 import allowlists), asserts the production + test
files exist, asserts the manifest edit is purely additive (the Stage 30.7.0
/ 30.7.1 / 30.7.2 constants survive) and is still constants-only, and
asserts the manifest exports the Stage 30.7.3 surface. The earlier-substage
constants are pinned by their own manifest / spec-lock tests and are not
re-pinned here.

Doc / constants only. No live call, no env read, no provider, no
Discord.
"""

from __future__ import annotations

import ast
from pathlib import Path

import PHX2.stage30.stage30_7_manifest as M
from PHX2.stage30.stage30_7_manifest import (
    STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
    STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_MODULE,
    STAGE30_7_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_7_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_7_3_MINOR_VERSION,
    STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME,
    STAGE30_7_3_SANITIZED_ATH_BRIDGE_MODULE,
    STAGE30_7_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_7_3_TEST_BASENAMES,
    STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_3,
    STAGE30_7_MANIFEST_BASENAME,
)
from PHX2.stage30.stage30_7_sanitized_ath_bridge import (
    STAGE30_7_3_MINOR_VERSION as BRIDGE_MINOR_VERSION,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Version
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_bridge() -> None:
    assert STAGE30_7_3_MINOR_VERSION == "30.7.3"
    assert STAGE30_7_3_MINOR_VERSION == BRIDGE_MINOR_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + inventory
# ---------------------------------------------------------------------------


def test_bridge_basename_pinned_and_exists() -> None:
    assert STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME == (
        "stage30_7_sanitized_ath_bridge.py"
    )
    path = STAGE30_ROOT / STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME
    assert path.is_file(), (
        f"Stage 30.7.3 requires "
        f"{STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME}"
    )


def test_bridge_module_path_pinned() -> None:
    assert STAGE30_7_3_SANITIZED_ATH_BRIDGE_MODULE == (
        "PHX2.stage30.stage30_7_sanitized_ath_bridge"
    )


def test_allowed_stage30_basenames_is_the_bridge() -> None:
    assert STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_3 == (
        STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME,
    )
    for basename in STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_3:
        assert (STAGE30_ROOT / basename).is_file()


def test_scanned_production_basenames_is_the_bridge() -> None:
    assert STAGE30_7_3_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME,
    )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_7_3_TEST_BASENAMES == (
        "test_stage_30_7_3_sanitized_ath_bridge.py",
        "test_stage_30_7_3_runtime_integration.py",
        "test_stage_30_7_3_boundaries.py",
        "test_stage_30_7_3_manifest.py",
    )
    for basename in STAGE30_7_3_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.7.3 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_7_3_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )


def test_phx2_import_allowlist_is_the_two_stage30_7_modules() -> None:
    assert STAGE30_7_3_ALLOWED_PHX2_IMPORTS == (
        STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
        STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_MODULE,
    )
    # No Stage 25 / 27 / 28 / 29 / Stage 30.1-30.6 runtime / renderer /
    # orchestrator path is admitted; every admitted module is a Stage 30.7
    # sibling.
    for module in STAGE30_7_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_7_")


# ---------------------------------------------------------------------------
# 4. Manifest edit is additive + still constants-only
# ---------------------------------------------------------------------------


def test_stage30_7_0_through_30_7_2_surface_survives() -> None:
    # The Stage 30.7.3 manifest edit is purely additive: the Stage 30.7.0 +
    # 30.7.1 + 30.7.2 surface the earlier tests import must remain in __all__.
    for name in (
        "STAGE30_7_MINOR_VERSION",
        "STAGE30_7_0_MINOR_VERSION",
        "STAGE30_7_SPEC_BASENAME",
        "STAGE30_7_MANIFEST_BASENAME",
        "STAGE30_7_SUBSTAGE_SEQUENCE",
        "STAGE30_7_FORBIDDEN_RUNTIME_IMPORTS",
        "STAGE30_7_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_7_1_MINOR_VERSION",
        "STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE",
        "STAGE30_7_1_ATH_CONTEXT_PROJECTION_MODULE",
        "STAGE30_7_2_MINOR_VERSION",
        "STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_MODULE",
        "STAGE30_7_2_ALLOWED_PHX2_IMPORTS",
    ):
        assert name in M.__all__, (
            f"30.7.0 / 30.7.1 / 30.7.2 surface {name!r} must survive"
        )


def test_manifest_still_constants_only() -> None:
    """AST proof that the additive 30.7.3 edit kept the manifest
    constants-only: no def / class / Call anywhere, only ``__future__`` +
    ``typing`` imports.
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
# 5. Manifest __all__ exports the Stage 30.7.3 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage30_7_3_surface() -> None:
    for name in (
        "STAGE30_7_3_MINOR_VERSION",
        "STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME",
        "STAGE30_7_3_SANITIZED_ATH_BRIDGE_MODULE",
        "STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_3",
        "STAGE30_7_3_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_7_3_TEST_BASENAMES",
        "STAGE30_7_3_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_7_3_ALLOWED_PHX2_IMPORTS",
    ):
        assert name in M.__all__, (
            f"manifest __all__ must export {name!r}"
        )
