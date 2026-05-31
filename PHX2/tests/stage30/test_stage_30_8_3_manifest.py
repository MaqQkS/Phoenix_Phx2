"""Stage 30.8.3 manifest pin tests.

Pins the Stage 30.8.3 manifest constants (minor version, index schema
version, mirrored bundle-format constants, the build / ping-dedupe / read
/ identity-kind closed sets, the three production basenames + module
paths, the inventory + scanned basenames, the test basenames, the stdlib +
PHX2 import allowlists, the forbidden surfaces, the next recommended
stage), asserts the production + test files exist, cross-checks the
mirrored constants against the Stage 30.8.3 models / reader and the Stage
30.8.2 writer, asserts the manifest exports the surface, asserts the
manifest stays constants-only (no def / class / Call; imports only
``__future__`` + ``typing``; no PHX2 import), asserts the Stage 30.8.0 /
30.8.1 / 30.8.2 constants survive, and re-pins the Stage 30.8.4+ future
guard.

Doc / constants only. No live call, no env read, no actual-disk read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import PHX2.stage30.stage30_8_manifest as M
from PHX2.stage30.stage30_8_manifest import (
    STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    STAGE30_8_2_BUNDLE_SCHEMA_VERSION,
    STAGE30_8_2_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_8_3_ALLOWED_STAGE30_BASENAMES,
    STAGE30_8_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_8_3_BUNDLE_MANIFEST_FILENAME,
    STAGE30_8_3_BUNDLE_VALIDATION_RESULT_FILENAME,
    STAGE30_8_3_DEDUPE_IDENTITY_KINDS,
    STAGE30_8_3_FORBIDDEN_SURFACES,
    STAGE30_8_3_INDEX_BUILD_STATUS_VALUES,
    STAGE30_8_3_INDEX_SCHEMA_VERSION,
    STAGE30_8_3_MINOR_VERSION,
    STAGE30_8_3_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_3_PING_DEDUPE_STATUS_VALUES,
    STAGE30_8_3_BUNDLE_READ_STATUS_VALUES,
    STAGE30_8_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_8_3_SESSION_BUNDLE_READER_BASENAME,
    STAGE30_8_3_SESSION_BUNDLE_READER_MODULE,
    STAGE30_8_3_SESSION_INDEX_BUILDER_BASENAME,
    STAGE30_8_3_SESSION_INDEX_BUILDER_MODULE,
    STAGE30_8_3_SESSION_INDEX_MODELS_BASENAME,
    STAGE30_8_3_SESSION_INDEX_MODELS_MODULE,
    STAGE30_8_3_TEST_BASENAMES,
    STAGE30_8_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_STAGE_ID,
)
from PHX2.stage30.stage30_8_session_index_models import (
    STAGE30_8_3_DEDUPE_IDENTITY_KINDS as MODELS_DEDUPE_IDENTITY_KINDS,
    STAGE30_8_3_INDEX_BUILD_STATUS_VALUES as MODELS_BUILD_STATUS_VALUES,
    STAGE30_8_3_INDEX_SCHEMA_VERSION as MODELS_INDEX_SCHEMA_VERSION,
    STAGE30_8_3_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_8_3_PING_DEDUPE_STATUS_VALUES as MODELS_PING_DEDUPE_STATUS_VALUES,
)
from PHX2.stage30.stage30_8_session_bundle_reader import (
    EXPECTED_BUNDLE_SCHEMA_VERSION as READER_EXPECTED_BUNDLE_SCHEMA_VERSION,
    MANIFEST_FILENAME as READER_MANIFEST_FILENAME,
    STAGE30_8_3_BUNDLE_READ_STATUS_VALUES as READER_READ_STATUS_VALUES,
    STAGE30_8_3_MINOR_VERSION as READER_MINOR_VERSION,
    VALIDATION_RESULT_FILENAME as READER_VALIDATION_RESULT_FILENAME,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    MANIFEST_FILENAME as WRITER_MANIFEST_FILENAME,
    STAGE30_8_2_BUNDLE_SCHEMA_VERSION as WRITER_BUNDLE_SCHEMA_VERSION,
    VALIDATION_RESULT_FILENAME as WRITER_VALIDATION_RESULT_FILENAME,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_8_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Versions + schema identity (mirrored from models / reader)
# ---------------------------------------------------------------------------


def test_minor_versions_pinned() -> None:
    assert STAGE30_8_STAGE_ID == "30.8"
    assert STAGE30_8_3_MINOR_VERSION == "30.8.3"
    assert STAGE30_8_3_MINOR_VERSION == MODELS_MINOR_VERSION
    assert STAGE30_8_3_MINOR_VERSION == READER_MINOR_VERSION


def test_index_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_8_3_INDEX_SCHEMA_VERSION == (
        "stage30_8_v0_compact_session_index"
    )
    assert STAGE30_8_3_INDEX_SCHEMA_VERSION == MODELS_INDEX_SCHEMA_VERSION


def test_bundle_format_constants_mirror_reader_and_writer() -> None:
    assert STAGE30_8_3_BUNDLE_MANIFEST_FILENAME == "manifest.json"
    assert STAGE30_8_3_BUNDLE_VALIDATION_RESULT_FILENAME == (
        "validation_result.json"
    )
    # The manifest mirror == the reader mirror == the Stage 30.8.2 writer.
    assert (
        STAGE30_8_3_BUNDLE_MANIFEST_FILENAME
        == READER_MANIFEST_FILENAME
        == WRITER_MANIFEST_FILENAME
    )
    assert (
        STAGE30_8_3_BUNDLE_VALIDATION_RESULT_FILENAME
        == READER_VALIDATION_RESULT_FILENAME
        == WRITER_VALIDATION_RESULT_FILENAME
    )
    # The reader expects exactly the Stage 30.8.2 bundle envelope schema.
    assert (
        READER_EXPECTED_BUNDLE_SCHEMA_VERSION
        == WRITER_BUNDLE_SCHEMA_VERSION
        == STAGE30_8_2_BUNDLE_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# 2. Closed-set status tokens (mirrored from models / reader)
# ---------------------------------------------------------------------------


def test_index_build_status_values_pinned_and_match_models() -> None:
    assert STAGE30_8_3_INDEX_BUILD_STATUS_VALUES == (
        "BUILT",
        "EMPTY",
        "INVALID_INPUT",
        "READ_FAILED",
        "INDEX_FAILED",
    )
    assert STAGE30_8_3_INDEX_BUILD_STATUS_VALUES == MODELS_BUILD_STATUS_VALUES


def test_ping_dedupe_status_values_pinned_and_match_models() -> None:
    assert STAGE30_8_3_PING_DEDUPE_STATUS_VALUES == (
        "RETAINED",
        "DUPLICATE_SUPPRESSED",
        "INVALID_SUPPRESSED",
    )
    assert (
        STAGE30_8_3_PING_DEDUPE_STATUS_VALUES
        == MODELS_PING_DEDUPE_STATUS_VALUES
    )


def test_bundle_read_status_values_pinned_and_match_reader() -> None:
    assert STAGE30_8_3_BUNDLE_READ_STATUS_VALUES == ("READ", "INVALID")
    assert STAGE30_8_3_BUNDLE_READ_STATUS_VALUES == READER_READ_STATUS_VALUES


def test_dedupe_identity_kinds_pinned_and_match_models() -> None:
    # dedupe_key is the ONLY retained identity (spec Section 9); there is
    # deliberately NO ping_id kind.
    assert STAGE30_8_3_DEDUPE_IDENTITY_KINDS == (
        "dedupe_key",
        "none",
    )
    assert "ping_id" not in STAGE30_8_3_DEDUPE_IDENTITY_KINDS
    assert STAGE30_8_3_DEDUPE_IDENTITY_KINDS == MODELS_DEDUPE_IDENTITY_KINDS


# ---------------------------------------------------------------------------
# 3. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_8_3_SESSION_INDEX_MODELS_BASENAME == (
        "stage30_8_session_index_models.py"
    )
    assert STAGE30_8_3_SESSION_BUNDLE_READER_BASENAME == (
        "stage30_8_session_bundle_reader.py"
    )
    assert STAGE30_8_3_SESSION_INDEX_BUILDER_BASENAME == (
        "stage30_8_session_index_builder.py"
    )
    assert STAGE30_8_3_SESSION_INDEX_MODELS_MODULE == (
        "PHX2.stage30.stage30_8_session_index_models"
    )
    assert STAGE30_8_3_SESSION_BUNDLE_READER_MODULE == (
        "PHX2.stage30.stage30_8_session_bundle_reader"
    )
    assert STAGE30_8_3_SESSION_INDEX_BUILDER_MODULE == (
        "PHX2.stage30.stage30_8_session_index_builder"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_8_3_SESSION_INDEX_MODELS_BASENAME,
        STAGE30_8_3_SESSION_BUNDLE_READER_BASENAME,
        STAGE30_8_3_SESSION_INDEX_BUILDER_BASENAME,
    )
    assert STAGE30_8_3_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_8_3_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_8_3_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.8.3 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_8_3_TEST_BASENAMES == (
        "test_stage_30_8_3_session_index_models.py",
        "test_stage_30_8_3_session_bundle_reader.py",
        "test_stage_30_8_3_session_index_builder.py",
        "test_stage_30_8_3_boundaries.py",
        "test_stage_30_8_3_manifest.py",
    )
    for basename in STAGE30_8_3_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.8.3 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 4. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_8_3_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "json",
        "pathlib",
    )
    assert "os" not in STAGE30_8_3_ALLOWED_STDLIB_IMPORTS
    assert "sqlite3" not in STAGE30_8_3_ALLOWED_STDLIB_IMPORTS
    assert "zstandard" not in STAGE30_8_3_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_the_three_siblings() -> None:
    assert STAGE30_8_3_ALLOWED_PHX2_IMPORTS == (
        STAGE30_8_3_SESSION_INDEX_MODELS_MODULE,
        STAGE30_8_3_SESSION_BUNDLE_READER_MODULE,
        STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    )
    for module in STAGE30_8_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_8_")


# ---------------------------------------------------------------------------
# 5. Forbidden surfaces + next recommended stage
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_8_3_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_8_3_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_8_3_FORBIDDEN_SURFACES)
    for token in (
        "real bot artifact directory",
        "default storage root",
        "index artifact write",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "compression implementation",
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
        "Stage 30.8.4+ implementation file",
    ):
        assert token in joined, (
            f"Stage 30.8.3 forbidden surfaces must name {token!r}"
        )


def test_next_recommended_stage_is_30_8_4() -> None:
    assert STAGE30_8_3_NEXT_RECOMMENDED_STAGE == "30.8.4"
    # The Stage 30.8.0 family pointer stays pinned at 30.8.1; the Stage
    # 30.8.2 pointer stays pinned at 30.8.3.
    assert STAGE30_8_NEXT_RECOMMENDED_STAGE == "30.8.1"
    assert STAGE30_8_2_NEXT_RECOMMENDED_STAGE == "30.8.3"


# ---------------------------------------------------------------------------
# 6. Manifest __all__ exports the Stage 30.8.3 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_surface() -> None:
    for name in (
        "STAGE30_8_3_MINOR_VERSION",
        "STAGE30_8_3_SESSION_INDEX_MODELS_BASENAME",
        "STAGE30_8_3_SESSION_INDEX_BUILDER_BASENAME",
        "STAGE30_8_3_SESSION_BUNDLE_READER_BASENAME",
        "STAGE30_8_3_SESSION_INDEX_MODELS_MODULE",
        "STAGE30_8_3_SESSION_INDEX_BUILDER_MODULE",
        "STAGE30_8_3_SESSION_BUNDLE_READER_MODULE",
        "STAGE30_8_3_INDEX_SCHEMA_VERSION",
        "STAGE30_8_3_BUNDLE_MANIFEST_FILENAME",
        "STAGE30_8_3_BUNDLE_VALIDATION_RESULT_FILENAME",
        "STAGE30_8_3_INDEX_BUILD_STATUS_VALUES",
        "STAGE30_8_3_PING_DEDUPE_STATUS_VALUES",
        "STAGE30_8_3_BUNDLE_READ_STATUS_VALUES",
        "STAGE30_8_3_DEDUPE_IDENTITY_KINDS",
        "STAGE30_8_3_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_8_3_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_8_3_TEST_BASENAMES",
        "STAGE30_8_3_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_8_3_ALLOWED_PHX2_IMPORTS",
        "STAGE30_8_3_FORBIDDEN_SURFACES",
        "STAGE30_8_3_NEXT_RECOMMENDED_STAGE",
        "STAGE30_8_3_NEXT_RECOMMENDED_STAGE_TITLE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_inventory_constants_still_present() -> None:
    # The Stage 30.8.3 manifest edit is purely additive: the Stage 30.8.0
    # / 30.8.1 / 30.8.2 constants the earlier pin tests import must remain.
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
        "STAGE30_8_2_MINOR_VERSION",
        "STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME",
        "STAGE30_8_2_BUNDLE_SCHEMA_VERSION",
        "STAGE30_8_2_NEXT_RECOMMENDED_STAGE",
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


# ---------------------------------------------------------------------------
# 8. Stage 30.8.4+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_8_MINOR_RE = re.compile(r"stage_?30_8_(\d+)")


def test_inventory_admits_no_stage_30_8_4_plus_file() -> None:
    inventory = (
        tuple(STAGE30_8_3_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_8_3_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_8_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 4:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.8.3 inventory must not admit a Stage 30.8.4+ file yet; "
        f"saw {violations!r}"
    )
