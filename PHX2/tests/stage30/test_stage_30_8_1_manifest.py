"""Stage 30.8.1 manifest pin tests.

Pins the Stage 30.8.1 manifest constants (minor version, artifact stage
id / schema version, basenames + module paths + inventory, scanned
production basenames, test basenames, stdlib + PHX2 import allowlists,
the mirrored artifact-kind / validation-status / budget-status closed
sets, the forbidden surfaces, the next recommended stage), asserts the
production + test files exist, cross-checks the mirrored closed sets /
identity constants against the Stage 30.8.1 models module, asserts the
manifest exports the surface, asserts the manifest stays constants-only
(no def / class / Call; imports only ``__future__`` + ``typing``; no
PHX2 import), and asserts the Stage 30.8.0 constants survive.

Doc / constants only. No live call, no env read, no actual-disk read.
"""

from __future__ import annotations

import ast
from pathlib import Path

import PHX2.stage30.stage30_8_manifest as M
from PHX2.stage30.stage30_8_manifest import (
    STAGE30_8_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_8_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_8_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_8_1_ARTIFACT_MODELS_BASENAME,
    STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    STAGE30_8_1_ARTIFACT_SCHEMA_VERSION,
    STAGE30_8_1_ARTIFACT_STAGE_ID,
    STAGE30_8_1_ARTIFACT_VALIDATORS_BASENAME,
    STAGE30_8_1_ARTIFACT_VALIDATORS_MODULE,
    STAGE30_8_1_FORBIDDEN_SURFACES,
    STAGE30_8_1_MINOR_VERSION,
    STAGE30_8_1_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_8_1_STORAGE_BUDGET_STATUS_VALUES,
    STAGE30_8_1_TEST_BASENAMES,
    STAGE30_8_1_VALIDATION_STATUS_VALUES,
    STAGE30_8_ARTIFACT_KINDS,
    STAGE30_8_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_STAGE_ID,
)
from PHX2.stage30.stage30_8_artifact_models import (
    STAGE30_8_1_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_8_ARTIFACT_KINDS as MODELS_ARTIFACT_KINDS,
    STAGE30_8_ARTIFACT_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_8_ARTIFACT_STAGE_ID as MODELS_STAGE_ID,
    STAGE30_8_STORAGE_BUDGET_STATUS_VALUES as MODELS_BUDGET_STATUSES,
    STAGE30_8_VALIDATION_STATUS_VALUES as MODELS_VALIDATION_STATUSES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_8_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Versions
# ---------------------------------------------------------------------------


def test_minor_versions_pinned() -> None:
    assert STAGE30_8_STAGE_ID == "30.8"
    assert STAGE30_8_1_MINOR_VERSION == "30.8.1"


def test_minor_version_matches_models() -> None:
    assert STAGE30_8_1_MINOR_VERSION == MODELS_MINOR_VERSION


# ---------------------------------------------------------------------------
# 2. Artifact schema identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_artifact_stage_id_pinned_and_matches_models() -> None:
    assert STAGE30_8_1_ARTIFACT_STAGE_ID == "stage30_8"
    assert STAGE30_8_1_ARTIFACT_STAGE_ID == MODELS_STAGE_ID
    # Distinct from the family dotted id.
    assert STAGE30_8_1_ARTIFACT_STAGE_ID != STAGE30_8_STAGE_ID


def test_artifact_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_8_1_ARTIFACT_SCHEMA_VERSION == (
        "stage30_8_v0_compact_artifact"
    )
    assert STAGE30_8_1_ARTIFACT_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


def test_artifact_kinds_match_models() -> None:
    assert STAGE30_8_ARTIFACT_KINDS == (
        "compact_session_summary",
        "compact_ping_artifact",
        "compact_dispatch_attempt_artifact",
        "compact_error_artifact",
        "compact_storage_budget_snapshot",
    )
    assert STAGE30_8_ARTIFACT_KINDS == MODELS_ARTIFACT_KINDS


def test_validation_status_values_match_models() -> None:
    assert STAGE30_8_1_VALIDATION_STATUS_VALUES == ("VALID", "INVALID")
    assert STAGE30_8_1_VALIDATION_STATUS_VALUES == (
        MODELS_VALIDATION_STATUSES
    )


def test_budget_status_values_match_models() -> None:
    assert STAGE30_8_1_STORAGE_BUDGET_STATUS_VALUES == (
        "OK",
        "SOFT_ALARM",
        "HARD_STOP",
        "INVALID_INPUT",
    )
    assert STAGE30_8_1_STORAGE_BUDGET_STATUS_VALUES == (
        MODELS_BUDGET_STATUSES
    )


# ---------------------------------------------------------------------------
# 3. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_production_basenames_pinned_and_exist() -> None:
    assert STAGE30_8_1_ARTIFACT_MODELS_BASENAME == (
        "stage30_8_artifact_models.py"
    )
    assert STAGE30_8_1_ARTIFACT_VALIDATORS_BASENAME == (
        "stage30_8_artifact_validators.py"
    )
    for basename in STAGE30_8_1_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.8.1 requires {basename}"
        )


def test_module_paths_pinned() -> None:
    assert STAGE30_8_1_ARTIFACT_MODELS_MODULE == (
        "PHX2.stage30.stage30_8_artifact_models"
    )
    assert STAGE30_8_1_ARTIFACT_VALIDATORS_MODULE == (
        "PHX2.stage30.stage30_8_artifact_validators"
    )


def test_allowed_stage30_basenames_is_the_two_modules() -> None:
    assert STAGE30_8_1_ALLOWED_STAGE30_BASENAMES == (
        STAGE30_8_1_ARTIFACT_MODELS_BASENAME,
        STAGE30_8_1_ARTIFACT_VALIDATORS_BASENAME,
    )


def test_scanned_production_basenames_are_the_two_modules() -> None:
    assert STAGE30_8_1_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_8_1_ARTIFACT_MODELS_BASENAME,
        STAGE30_8_1_ARTIFACT_VALIDATORS_BASENAME,
    )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_8_1_TEST_BASENAMES == (
        "test_stage_30_8_1_artifact_models.py",
        "test_stage_30_8_1_artifact_validators.py",
        "test_stage_30_8_1_boundaries.py",
        "test_stage_30_8_1_manifest.py",
    )
    for basename in STAGE30_8_1_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.8.1 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 4. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_8_1_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "math",
    )


def test_phx2_import_allowlist_is_only_the_models_sibling() -> None:
    assert STAGE30_8_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    )
    for module in STAGE30_8_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_8_")


# ---------------------------------------------------------------------------
# 5. Forbidden surfaces + next recommended stage
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_8_1_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_8_1_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_8_1_FORBIDDEN_SURFACES)
    for token in (
        "writer implementation",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "compression implementation",
        "live run",
        "provider call",
        "Discord send",
        "runtime orchestrator edit",
        "compact renderer edit",
        "Stage 30.7 file edit",
        "Stage 25/27/28/29 production import",
        "Stage 29.5 production import",
        "trading",
        "wallet",
        "drawdown recomputation",
        "tier recomputation",
        "commit",
        "tag",
        "push",
        "Stage 30.8.2+ implementation file",
    ):
        assert token in joined, (
            f"Stage 30.8.1 forbidden surfaces must name {token!r}"
        )


def test_next_recommended_stage_is_30_8_2() -> None:
    assert STAGE30_8_1_NEXT_RECOMMENDED_STAGE == "30.8.2"
    # The Stage 30.8.0 family pointer stays pinned at 30.8.1.
    assert STAGE30_8_NEXT_RECOMMENDED_STAGE == "30.8.1"


# ---------------------------------------------------------------------------
# 6. Manifest __all__ exports the Stage 30.8.1 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_surface() -> None:
    for name in (
        "STAGE30_8_1_MINOR_VERSION",
        "STAGE30_8_1_ARTIFACT_MODELS_BASENAME",
        "STAGE30_8_1_ARTIFACT_VALIDATORS_BASENAME",
        "STAGE30_8_1_ARTIFACT_MODELS_MODULE",
        "STAGE30_8_1_ARTIFACT_VALIDATORS_MODULE",
        "STAGE30_8_1_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_8_1_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_8_1_TEST_BASENAMES",
        "STAGE30_8_1_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_8_1_ALLOWED_PHX2_IMPORTS",
        "STAGE30_8_1_ARTIFACT_STAGE_ID",
        "STAGE30_8_1_ARTIFACT_SCHEMA_VERSION",
        "STAGE30_8_1_VALIDATION_STATUS_VALUES",
        "STAGE30_8_1_STORAGE_BUDGET_STATUS_VALUES",
        "STAGE30_8_1_FORBIDDEN_SURFACES",
        "STAGE30_8_1_NEXT_RECOMMENDED_STAGE",
        "STAGE30_8_1_NEXT_RECOMMENDED_STAGE_TITLE",
    ):
        assert name in M.__all__, (
            f"manifest __all__ must export {name!r}"
        )


def test_stage30_8_0_inventory_constants_still_present() -> None:
    # The Stage 30.8.1 manifest edit is purely additive: the Stage
    # 30.8.0 constants the 30.8.0 pin test imports must remain.
    for name in (
        "STAGE30_8_STAGE_ID",
        "STAGE30_8_0_MINOR_VERSION",
        "STAGE30_8_ALLOWED_INITIAL_FILES",
        "STAGE30_8_ARTIFACT_KINDS",
        "STAGE30_8_IDENTITY_FIELDS",
        "STAGE30_8_NEXT_RECOMMENDED_STAGE",
        "STAGE30_8_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 7. Manifest stays constants-only + imports no PHX2 module
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
