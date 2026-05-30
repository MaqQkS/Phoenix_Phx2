"""Stage 30.8.2 manifest pin tests.

Pins the Stage 30.8.2 manifest constants (minor version, bundle schema
version, write-status closed set, writer basename + module path,
inventory + scanned basenames, test basenames, stdlib + PHX2 import
allowlists, the forbidden surfaces, the next recommended stage), asserts
the production + test files exist, cross-checks the mirrored constants
against the Stage 30.8.2 writer module, asserts the manifest exports the
surface, asserts the manifest stays constants-only (no def / class /
Call; imports only ``__future__`` + ``typing``; no PHX2 import), and
asserts the Stage 30.8.0 / 30.8.1 constants survive.

Doc / constants only. No live call, no env read, no actual-disk read.
"""

from __future__ import annotations

import ast
from pathlib import Path

import PHX2.stage30.stage30_8_manifest as M
from PHX2.stage30.stage30_8_manifest import (
    STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    STAGE30_8_1_ARTIFACT_VALIDATORS_MODULE,
    STAGE30_8_2_ALLOWED_PHX2_IMPORTS,
    STAGE30_8_2_ALLOWED_STAGE30_BASENAMES,
    STAGE30_8_2_ALLOWED_STDLIB_IMPORTS,
    STAGE30_8_2_BUNDLE_SCHEMA_VERSION,
    STAGE30_8_2_FORBIDDEN_SURFACES,
    STAGE30_8_2_MINOR_VERSION,
    STAGE30_8_2_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_2_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME,
    STAGE30_8_2_TEMP_ARTIFACT_WRITER_MODULE,
    STAGE30_8_2_TEST_BASENAMES,
    STAGE30_8_2_WRITE_STATUS_VALUES,
    STAGE30_8_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_STAGE_ID,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    STAGE30_8_2_BUNDLE_SCHEMA_VERSION as WRITER_BUNDLE_SCHEMA_VERSION,
    STAGE30_8_2_MINOR_VERSION as WRITER_MINOR_VERSION,
    STAGE30_8_2_WRITE_STATUS_VALUES as WRITER_WRITE_STATUS_VALUES,
    WRITE_STATUS_INVALID,
    WRITE_STATUS_WRITE_FAILED,
    WRITE_STATUS_WRITTEN,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_8_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Versions + bundle schema identity (mirrored from the writer)
# ---------------------------------------------------------------------------


def test_minor_versions_pinned() -> None:
    assert STAGE30_8_STAGE_ID == "30.8"
    assert STAGE30_8_2_MINOR_VERSION == "30.8.2"


def test_minor_version_matches_writer() -> None:
    assert STAGE30_8_2_MINOR_VERSION == WRITER_MINOR_VERSION


def test_bundle_schema_version_pinned_and_matches_writer() -> None:
    assert STAGE30_8_2_BUNDLE_SCHEMA_VERSION == (
        "stage30_8_v0_compact_session_bundle"
    )
    assert STAGE30_8_2_BUNDLE_SCHEMA_VERSION == WRITER_BUNDLE_SCHEMA_VERSION


def test_write_status_values_pinned_and_match_writer() -> None:
    assert STAGE30_8_2_WRITE_STATUS_VALUES == (
        "WRITTEN",
        "INVALID",
        "WRITE_FAILED",
    )
    assert STAGE30_8_2_WRITE_STATUS_VALUES == WRITER_WRITE_STATUS_VALUES
    assert STAGE30_8_2_WRITE_STATUS_VALUES == (
        WRITE_STATUS_WRITTEN,
        WRITE_STATUS_INVALID,
        WRITE_STATUS_WRITE_FAILED,
    )


# ---------------------------------------------------------------------------
# 2. Basenames + module path + inventory
# ---------------------------------------------------------------------------


def test_writer_basename_and_module_pinned() -> None:
    assert STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME == (
        "stage30_8_temp_artifact_writer.py"
    )
    assert STAGE30_8_2_TEMP_ARTIFACT_WRITER_MODULE == (
        "PHX2.stage30.stage30_8_temp_artifact_writer"
    )


def test_allowed_stage30_basenames_is_the_writer() -> None:
    assert STAGE30_8_2_ALLOWED_STAGE30_BASENAMES == (
        STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME,
    )


def test_scanned_production_basenames_are_the_writer() -> None:
    assert STAGE30_8_2_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME,
    )


def test_production_file_exists() -> None:
    for basename in STAGE30_8_2_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.8.2 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_8_2_TEST_BASENAMES == (
        "test_stage_30_8_2_temp_artifact_writer.py",
        "test_stage_30_8_2_boundaries.py",
        "test_stage_30_8_2_manifest.py",
    )
    for basename in STAGE30_8_2_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.8.2 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    # The writer legitimately needs json + pathlib + re (it writes JSON to
    # a caller temp dir); it does NOT get os (no env read).
    assert STAGE30_8_2_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "json",
        "pathlib",
        "re",
    )
    assert "os" not in STAGE30_8_2_ALLOWED_STDLIB_IMPORTS
    assert "sqlite3" not in STAGE30_8_2_ALLOWED_STDLIB_IMPORTS
    assert "zstandard" not in STAGE30_8_2_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_the_two_siblings() -> None:
    assert STAGE30_8_2_ALLOWED_PHX2_IMPORTS == (
        STAGE30_8_1_ARTIFACT_MODELS_MODULE,
        STAGE30_8_1_ARTIFACT_VALIDATORS_MODULE,
    )
    for module in STAGE30_8_2_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_8_")


# ---------------------------------------------------------------------------
# 4. Forbidden surfaces + next recommended stage
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_8_2_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_8_2_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_8_2_FORBIDDEN_SURFACES)
    for token in (
        "real bot artifact directory",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "compression implementation",
        "dedupe index implementation",
        "session index implementation",
        "append-only database",
        "live run",
        "provider call",
        "Discord send",
        "env read",
        "runtime orchestrator edit",
        "compact renderer edit",
        "Stage 30.7 file edit",
        "Stage 25/27/28/29 production import",
        "Stage 29.5 production import",
        "trading",
        "wallet",
        "commit",
        "tag",
        "push",
        "Stage 30.8.3+ implementation file",
    ):
        assert token in joined, (
            f"Stage 30.8.2 forbidden surfaces must name {token!r}"
        )


def test_next_recommended_stage_is_30_8_3() -> None:
    assert STAGE30_8_2_NEXT_RECOMMENDED_STAGE == "30.8.3"
    # The Stage 30.8.0 family pointer stays pinned at 30.8.1.
    assert STAGE30_8_NEXT_RECOMMENDED_STAGE == "30.8.1"


# ---------------------------------------------------------------------------
# 5. Manifest __all__ exports the Stage 30.8.2 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_surface() -> None:
    for name in (
        "STAGE30_8_2_MINOR_VERSION",
        "STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME",
        "STAGE30_8_2_TEMP_ARTIFACT_WRITER_MODULE",
        "STAGE30_8_2_BUNDLE_SCHEMA_VERSION",
        "STAGE30_8_2_WRITE_STATUS_VALUES",
        "STAGE30_8_2_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_8_2_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_8_2_TEST_BASENAMES",
        "STAGE30_8_2_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_8_2_ALLOWED_PHX2_IMPORTS",
        "STAGE30_8_2_FORBIDDEN_SURFACES",
        "STAGE30_8_2_NEXT_RECOMMENDED_STAGE",
        "STAGE30_8_2_NEXT_RECOMMENDED_STAGE_TITLE",
    ):
        assert name in M.__all__, (
            f"manifest __all__ must export {name!r}"
        )


def test_stage30_8_0_and_30_8_1_inventory_constants_still_present() -> None:
    # The Stage 30.8.2 manifest edit is purely additive: the Stage 30.8.0
    # + 30.8.1 constants the earlier pin tests import must remain.
    for name in (
        "STAGE30_8_STAGE_ID",
        "STAGE30_8_0_MINOR_VERSION",
        "STAGE30_8_ALLOWED_INITIAL_FILES",
        "STAGE30_8_ARTIFACT_KINDS",
        "STAGE30_8_IDENTITY_FIELDS",
        "STAGE30_8_NEXT_RECOMMENDED_STAGE",
        "STAGE30_8_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_8_1_MINOR_VERSION",
        "STAGE30_8_1_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_8_1_NEXT_RECOMMENDED_STAGE",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 6. Manifest stays constants-only + imports no PHX2 module
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only() -> None:
    tree = ast.parse(_manifest_text())
    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), "Stage 30.8 manifest must be constants-only (no def / class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.8 manifest must be constants-only (no Call)"
        )
    allowed_import_roots = {"__future__", "typing"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.8 manifest may import only __future__ / "
                f"typing; saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.8 manifest may import only __future__ / "
                    f"typing; saw {alias.name!r}"
                )


def test_manifest_imports_no_phx2_module() -> None:
    tree = ast.parse(_manifest_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("PHX2"), (
                f"Stage 30.8 manifest imports PHX2 module {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("PHX2"), (
                    f"Stage 30.8 manifest imports PHX2 module "
                    f"{alias.name!r}"
                )
