"""Stage 30.5.2 manifest pin tests.

Pins the Stage 30.5.2 manifest constants (minor version, runtime
adapter basename + module path, inventory + scanned basenames, test
basenames, stdlib + PHX2 import allowlists), asserts the production +
test files exist, and asserts the manifest exports the Stage 30.5.2
surface. The Stage 30.5.1 constants are pinned by
``test_stage_30_5_1_manifest.py`` and are not re-pinned here.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_5_manifest as M
from PHX2.stage30.stage30_5_compact_migration_runtime_adapter import (
    STAGE30_5_2_MINOR_VERSION as ADAPTER_MINOR_VERSION,
)
from PHX2.stage30.stage30_5_manifest import (
    STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_MODULE,
    STAGE30_5_1_MIGRATION_CONTEXT_MODELS_MODULE,
    STAGE30_5_2_ALLOWED_PHX2_IMPORTS,
    STAGE30_5_2_ALLOWED_STDLIB_IMPORTS,
    STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME,
    STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_MODULE,
    STAGE30_5_2_MINOR_VERSION,
    STAGE30_5_2_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_5_2_TEST_BASENAMES,
    STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_2,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Version
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_adapter() -> None:
    assert STAGE30_5_2_MINOR_VERSION == "30.5.2"
    assert STAGE30_5_2_MINOR_VERSION == ADAPTER_MINOR_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + inventory
# ---------------------------------------------------------------------------


def test_runtime_adapter_basename_pinned_and_exists() -> None:
    assert STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME == (
        "stage30_5_compact_migration_runtime_adapter.py"
    )
    path = (
        STAGE30_ROOT
        / STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME
    )
    assert path.is_file(), (
        f"Stage 30.5.2 requires "
        f"{STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME}"
    )


def test_runtime_adapter_module_path_pinned() -> None:
    assert STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_5_compact_migration_runtime_adapter"
    )


def test_allowed_stage30_basenames_is_the_runtime_adapter() -> None:
    assert STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_2 == (
        STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME,
    )
    for basename in STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_2:
        assert (STAGE30_ROOT / basename).is_file()


def test_scanned_production_basenames_is_the_runtime_adapter() -> None:
    assert STAGE30_5_2_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME,
    )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_5_2_TEST_BASENAMES == (
        "test_stage_30_5_2_compact_migration_runtime_adapter.py",
        "test_stage_30_5_2_runtime_integration.py",
        "test_stage_30_5_2_boundaries.py",
        "test_stage_30_5_2_manifest.py",
    )
    for basename in STAGE30_5_2_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.5.2 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_5_2_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
    )


def test_phx2_import_allowlist_is_the_two_stage30_5_1_modules() -> None:
    assert STAGE30_5_2_ALLOWED_PHX2_IMPORTS == (
        STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_MODULE,
        STAGE30_5_1_MIGRATION_CONTEXT_MODELS_MODULE,
    )
    # No Stage 29 / Stage 28 / Stage 30.1-30.4 path is admitted; every
    # admitted module is a Stage 30.5.1 sibling.
    for module in STAGE30_5_2_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_5_")


# ---------------------------------------------------------------------------
# 4. Manifest __all__ exports the Stage 30.5.2 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage30_5_2_surface() -> None:
    for name in (
        "STAGE30_5_2_MINOR_VERSION",
        "STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME",
        "STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_MODULE",
        "STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_2",
        "STAGE30_5_2_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_5_2_TEST_BASENAMES",
        "STAGE30_5_2_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_5_2_ALLOWED_PHX2_IMPORTS",
    ):
        assert name in M.__all__, (
            f"manifest __all__ must export {name!r}"
        )
