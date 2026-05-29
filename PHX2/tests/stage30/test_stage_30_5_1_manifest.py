"""Stage 30.5.1 manifest pin tests.

Pins the Stage 30.5.1 manifest constants (minor versions, schema
version, basenames + allowlist, scanned production basenames, test
basenames, stdlib + PHX2 import allowlists, the Stage 29.5.5 must-
not-import surface), asserts the production + test files exist,
asserts the manifest exports the surface, and asserts the forbidden
import / text needle sets are not empty.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_5_manifest as M
from PHX2.stage30.stage30_5_migration_context_models import (
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
)
from PHX2.stage30.stage30_5_manifest import (
    STAGE30_5_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_5_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_BASENAME,
    STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_MODULE,
    STAGE30_5_1_MIGRATION_CONTEXT_MODELS_BASENAME,
    STAGE30_5_1_MIGRATION_CONTEXT_MODELS_MODULE,
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
    STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_BASENAME,
    STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_MODULE,
    STAGE30_5_1_MINOR_VERSION,
    STAGE30_5_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_5_1_TEST_BASENAMES,
    STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_1,
    STAGE30_5_FORBIDDEN_RUNTIME_IMPORTS,
    STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES,
    STAGE30_5_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_5_MANIFEST_BASENAME,
    STAGE30_5_MINOR_VERSION,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Versions + schema version
# ---------------------------------------------------------------------------


def test_minor_versions_pinned() -> None:
    assert STAGE30_5_MINOR_VERSION == "30.5"
    assert STAGE30_5_1_MINOR_VERSION == "30.5.1"


def test_schema_version_pinned_and_matches_models() -> None:
    assert (
        STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION
        == "stage30_5_1_v0_migration_context"
    )
    assert (
        STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION
        == MODELS_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# 2. Basenames + inventory
# ---------------------------------------------------------------------------


def test_production_basenames_pinned_and_exist() -> None:
    assert STAGE30_5_MANIFEST_BASENAME == "stage30_5_manifest.py"
    assert STAGE30_5_1_MIGRATION_CONTEXT_MODELS_BASENAME == (
        "stage30_5_migration_context_models.py"
    )
    assert STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_BASENAME == (
        "stage30_5_migration_context_source_protocol.py"
    )
    assert STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_BASENAME == (
        "stage30_5_migration_context_adapter.py"
    )
    for basename in STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_1:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.5.1 requires {basename}"
        )


def test_allowed_stage30_basenames_is_three_modules_plus_manifest() -> None:
    assert STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_1 == (
        STAGE30_5_1_MIGRATION_CONTEXT_MODELS_BASENAME,
        STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_BASENAME,
        STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_BASENAME,
        STAGE30_5_MANIFEST_BASENAME,
    )


def test_scanned_production_basenames_are_the_three_modules() -> None:
    assert STAGE30_5_1_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_5_1_MIGRATION_CONTEXT_MODELS_BASENAME,
        STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_BASENAME,
        STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_BASENAME,
    )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_5_1_TEST_BASENAMES == (
        "test_stage_30_5_1_migration_context_models.py",
        "test_stage_30_5_1_migration_context_source_protocol.py",
        "test_stage_30_5_1_migration_context_adapter.py",
        "test_stage_30_5_1_boundaries.py",
        "test_stage_30_5_1_manifest.py",
    )
    for basename in STAGE30_5_1_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.5.1 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_5_1_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "re",
    )


def test_phx2_import_allowlist_is_the_three_sibling_modules() -> None:
    assert STAGE30_5_1_MIGRATION_CONTEXT_MODELS_MODULE == (
        "PHX2.stage30.stage30_5_migration_context_models"
    )
    assert STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_MODULE == (
        "PHX2.stage30.stage30_5_migration_context_source_protocol"
    )
    assert STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_5_migration_context_adapter"
    )
    assert STAGE30_5_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_5_1_MIGRATION_CONTEXT_MODELS_MODULE,
        STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_MODULE,
        STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_MODULE,
    )
    # No Stage 29 / Stage 28 path is admitted into the allowlist.
    for module in STAGE30_5_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_5_")


# ---------------------------------------------------------------------------
# 4. Stage 29.5.5 must-not-import surface
# ---------------------------------------------------------------------------


def test_forbidden_stage29_5_5_modules_documented() -> None:
    assert len(STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES) == 3
    for module in STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES:
        assert module.startswith("PHX2.stage29.stage29_5_5_")
    # The three side-channel surfaces (renderer / recorder / writer).
    assert any(
        m.endswith("_migration_context_renderer")
        for m in STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES
    )
    assert (
        "PHX2.stage29.stage29_5_5_migration_context_recorder"
        in STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES
    )
    assert (
        "PHX2.stage29.stage29_5_5_side_channel_artifact_writer"
        in STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES
    )


# ---------------------------------------------------------------------------
# 5. Forbidden import / text needle sets are populated
# ---------------------------------------------------------------------------


def test_forbidden_runtime_import_set_populated() -> None:
    assert len(STAGE30_5_FORBIDDEN_RUNTIME_IMPORTS) >= 20
    for needle in ("os.environ", "import socket", "from urllib"):
        assert needle in STAGE30_5_FORBIDDEN_RUNTIME_IMPORTS
    assert "from PHX2.stage29" in STAGE30_5_FORBIDDEN_RUNTIME_IMPORTS


def test_forbidden_text_needle_set_populated() -> None:
    assert len(STAGE30_5_FORBIDDEN_TEXT_NEEDLES) >= 12


# ---------------------------------------------------------------------------
# 6. Manifest __all__ exports the surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_surface() -> None:
    for name in (
        "STAGE30_5_MINOR_VERSION",
        "STAGE30_5_1_MINOR_VERSION",
        "STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION",
        "STAGE30_5_MANIFEST_BASENAME",
        "STAGE30_5_1_MIGRATION_CONTEXT_MODELS_BASENAME",
        "STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_BASENAME",
        "STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_BASENAME",
        "STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_1",
        "STAGE30_5_1_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_5_1_TEST_BASENAMES",
        "STAGE30_5_1_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_5_1_ALLOWED_PHX2_IMPORTS",
        "STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES",
        "STAGE30_5_FORBIDDEN_RUNTIME_IMPORTS",
        "STAGE30_5_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__, (
            f"manifest __all__ must export {name!r}"
        )
