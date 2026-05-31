"""Stage 30.8.4 manifest pin tests.

Pins the Stage 30.8.4 manifest constants (minor version, proof schema
version, default scenario name, the proof status / reason closed sets, the
author-verified expected counts, the two production basenames + module
paths, the inventory + scanned basenames, the test basenames, the stdlib +
PHX2 import allowlists, the forbidden surfaces, the next recommended
stage), asserts the production + test files exist, cross-checks the
mirrored constants against the Stage 30.8.4 proof models (including the
default scenario's expected counts), asserts the manifest exports the
surface, asserts the manifest stays constants-only (no def / class / Call;
imports only ``__future__`` + ``typing``; no PHX2 import), asserts the
Stage 30.8.0 / 30.8.1 / 30.8.2 / 30.8.3 constants survive, and pins the
Stage 30.8.5+ future guard.

Doc / constants only. No live call, no env read, no actual-disk read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import PHX2.stage30.stage30_8_manifest as M
from PHX2.stage30.stage30_8_manifest import (
    STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    STAGE30_8_2_TEMP_ARTIFACT_WRITER_MODULE,
    STAGE30_8_3_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_3_SESSION_BUNDLE_READER_MODULE,
    STAGE30_8_3_SESSION_INDEX_BUILDER_MODULE,
    STAGE30_8_3_SESSION_INDEX_MODELS_MODULE,
    STAGE30_8_4_ALLOWED_PHX2_IMPORTS,
    STAGE30_8_4_ALLOWED_STAGE30_BASENAMES,
    STAGE30_8_4_ALLOWED_STDLIB_IMPORTS,
    STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_BASENAME,
    STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODELS_BASENAME,
    STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODELS_MODULE,
    STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODULE,
    STAGE30_8_4_DEFAULT_SCENARIO_NAME,
    STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED,
    STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED,
    STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN,
    STAGE30_8_4_EXPECTED_RETAINED,
    STAGE30_8_4_EXPECTED_SESSIONS_WRITTEN,
    STAGE30_8_4_FORBIDDEN_SURFACES,
    STAGE30_8_4_MINOR_VERSION,
    STAGE30_8_4_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_4_PROOF_REASONS,
    STAGE30_8_4_PROOF_SCHEMA_VERSION,
    STAGE30_8_4_PROOF_STATUS_VALUES,
    STAGE30_8_4_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_8_4_TEST_BASENAMES,
    STAGE30_8_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_STAGE_ID,
)
from PHX2.stage30.stage30_8_controlled_artifact_proof_models import (
    STAGE30_8_4_DEFAULT_SCENARIO_NAME as MODELS_DEFAULT_SCENARIO_NAME,
    STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED as MODELS_EXPECTED_DUP,
    STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED as MODELS_EXPECTED_INVALID,
    STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN as MODELS_EXPECTED_PINGS,
    STAGE30_8_4_EXPECTED_RETAINED as MODELS_EXPECTED_RETAINED,
    STAGE30_8_4_EXPECTED_SESSIONS_WRITTEN as MODELS_EXPECTED_SESSIONS,
    STAGE30_8_4_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_8_4_PROOF_REASONS as MODELS_PROOF_REASONS,
    STAGE30_8_4_PROOF_SCHEMA_VERSION as MODELS_PROOF_SCHEMA_VERSION,
    STAGE30_8_4_PROOF_STATUS_VALUES as MODELS_PROOF_STATUS_VALUES,
    default_proof_scenario,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_8_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Versions + schema identity + scenario name (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_8_STAGE_ID == "30.8"
    assert STAGE30_8_4_MINOR_VERSION == "30.8.4"
    assert STAGE30_8_4_MINOR_VERSION == MODELS_MINOR_VERSION


def test_proof_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_8_4_PROOF_SCHEMA_VERSION == (
        "stage30_8_v0_compact_session_proof"
    )
    assert STAGE30_8_4_PROOF_SCHEMA_VERSION == MODELS_PROOF_SCHEMA_VERSION


def test_default_scenario_name_pinned_and_matches_models() -> None:
    assert STAGE30_8_4_DEFAULT_SCENARIO_NAME == (
        "stage30_8_4_default_dedupe_mismatch"
    )
    assert STAGE30_8_4_DEFAULT_SCENARIO_NAME == MODELS_DEFAULT_SCENARIO_NAME


# ---------------------------------------------------------------------------
# 2. Closed-set status / reason tokens (mirrored from models)
# ---------------------------------------------------------------------------


def test_proof_status_values_pinned_and_match_models() -> None:
    assert STAGE30_8_4_PROOF_STATUS_VALUES == ("PROVED", "FAILED")
    assert STAGE30_8_4_PROOF_STATUS_VALUES == MODELS_PROOF_STATUS_VALUES


def test_proof_reasons_pinned_and_match_models() -> None:
    assert STAGE30_8_4_PROOF_REASONS == (
        "OK",
        "INVALID_OUTPUT_DIR",
        "INVALID_SCENARIO",
        "WRITE_FAILED",
        "READ_FAILED",
        "INDEX_FAILED",
        "COUNT_MISMATCH",
        "INVARIANT_FAILED",
    )
    assert STAGE30_8_4_PROOF_REASONS == MODELS_PROOF_REASONS


# ---------------------------------------------------------------------------
# 3. Expected counts (mirrored from models + the live default scenario)
# ---------------------------------------------------------------------------


def test_expected_counts_pinned_and_match_models() -> None:
    assert STAGE30_8_4_EXPECTED_SESSIONS_WRITTEN == 2
    assert STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN == 6
    assert STAGE30_8_4_EXPECTED_RETAINED == 3
    assert STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED == 2
    assert STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED == 1
    assert STAGE30_8_4_EXPECTED_SESSIONS_WRITTEN == MODELS_EXPECTED_SESSIONS
    assert STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN == MODELS_EXPECTED_PINGS
    assert STAGE30_8_4_EXPECTED_RETAINED == MODELS_EXPECTED_RETAINED
    assert (
        STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED == MODELS_EXPECTED_DUP
    )
    assert STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED == MODELS_EXPECTED_INVALID


def test_expected_counts_match_default_scenario() -> None:
    # The manifest oracle must match the scenario the runner actually
    # builds (and its internal consistency: retained + duplicate + invalid
    # == ping artifacts).
    scenario = default_proof_scenario()
    assert scenario.expected_sessions_written == (
        STAGE30_8_4_EXPECTED_SESSIONS_WRITTEN
    )
    assert scenario.expected_ping_artifacts_seen == (
        STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN
    )
    assert scenario.expected_retained == STAGE30_8_4_EXPECTED_RETAINED
    assert scenario.expected_duplicate_suppressed == (
        STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED
    )
    assert scenario.expected_invalid_suppressed == (
        STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED
    )
    assert len(scenario.pings) == STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN
    assert (
        STAGE30_8_4_EXPECTED_RETAINED
        + STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED
        + STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED
        == STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN
    )


# ---------------------------------------------------------------------------
# 4. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODELS_BASENAME == (
        "stage30_8_controlled_artifact_proof_models.py"
    )
    assert STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_BASENAME == (
        "stage30_8_controlled_artifact_proof.py"
    )
    assert STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODELS_MODULE == (
        "PHX2.stage30.stage30_8_controlled_artifact_proof_models"
    )
    assert STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODULE == (
        "PHX2.stage30.stage30_8_controlled_artifact_proof"
    )


def test_allowed_and_scanned_basenames_are_the_two_modules() -> None:
    expected = (
        STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODELS_BASENAME,
        STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_BASENAME,
    )
    assert STAGE30_8_4_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_8_4_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_8_4_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.8.4 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_8_4_TEST_BASENAMES == (
        "test_stage_30_8_4_controlled_artifact_proof.py",
        "test_stage_30_8_4_boundaries.py",
        "test_stage_30_8_4_manifest.py",
    )
    for basename in STAGE30_8_4_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.8.4 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 5. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_8_4_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    assert "os" not in STAGE30_8_4_ALLOWED_STDLIB_IMPORTS
    assert "json" not in STAGE30_8_4_ALLOWED_STDLIB_IMPORTS
    assert "pathlib" not in STAGE30_8_4_ALLOWED_STDLIB_IMPORTS
    assert "sqlite3" not in STAGE30_8_4_ALLOWED_STDLIB_IMPORTS
    assert "zstandard" not in STAGE30_8_4_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_the_six_siblings() -> None:
    assert STAGE30_8_4_ALLOWED_PHX2_IMPORTS == (
        STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODELS_MODULE,
        STAGE30_8_1_ARTIFACT_MODELS_MODULE,
        STAGE30_8_2_TEMP_ARTIFACT_WRITER_MODULE,
        STAGE30_8_3_SESSION_BUNDLE_READER_MODULE,
        STAGE30_8_3_SESSION_INDEX_BUILDER_MODULE,
        STAGE30_8_3_SESSION_INDEX_MODELS_MODULE,
    )
    for module in STAGE30_8_4_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_8_")


# ---------------------------------------------------------------------------
# 6. Forbidden surfaces + next recommended stage
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_8_4_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_8_4_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_8_4_FORBIDDEN_SURFACES)
    for token in (
        "real bot artifact directory",
        "default storage root",
        "proof summary default path",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "compression implementation",
        "live run",
        "live provider run",
        "provider call",
        "Discord send",
        "env read",
        "runtime integration",
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
        "Stage 30.9 implementation file",
        "Stage 30.8.5+ implementation file",
    ):
        assert token in joined, (
            f"Stage 30.8.4 forbidden surfaces must name {token!r}"
        )


def test_next_recommended_stage_is_30_9_and_earlier_pointers_intact() -> None:
    assert STAGE30_8_4_NEXT_RECOMMENDED_STAGE == "30.9"
    # The Stage 30.8.0 family pointer stays pinned at 30.8.1; the Stage
    # 30.8.3 pointer stays pinned at 30.8.4.
    assert STAGE30_8_NEXT_RECOMMENDED_STAGE == "30.8.1"
    assert STAGE30_8_3_NEXT_RECOMMENDED_STAGE == "30.8.4"


# ---------------------------------------------------------------------------
# 7. Manifest __all__ exports the Stage 30.8.4 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_surface() -> None:
    for name in (
        "STAGE30_8_4_MINOR_VERSION",
        "STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODELS_BASENAME",
        "STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_BASENAME",
        "STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODELS_MODULE",
        "STAGE30_8_4_CONTROLLED_ARTIFACT_PROOF_MODULE",
        "STAGE30_8_4_PROOF_SCHEMA_VERSION",
        "STAGE30_8_4_DEFAULT_SCENARIO_NAME",
        "STAGE30_8_4_PROOF_STATUS_VALUES",
        "STAGE30_8_4_PROOF_REASONS",
        "STAGE30_8_4_EXPECTED_SESSIONS_WRITTEN",
        "STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN",
        "STAGE30_8_4_EXPECTED_RETAINED",
        "STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED",
        "STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED",
        "STAGE30_8_4_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_8_4_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_8_4_TEST_BASENAMES",
        "STAGE30_8_4_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_8_4_ALLOWED_PHX2_IMPORTS",
        "STAGE30_8_4_FORBIDDEN_SURFACES",
        "STAGE30_8_4_NEXT_RECOMMENDED_STAGE",
        "STAGE30_8_4_NEXT_RECOMMENDED_STAGE_TITLE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_inventory_constants_still_present() -> None:
    # The Stage 30.8.4 manifest edit is purely additive: the Stage 30.8.0
    # / 30.8.1 / 30.8.2 / 30.8.3 constants the earlier pin tests import
    # must remain.
    for name in (
        "STAGE30_8_STAGE_ID",
        "STAGE30_8_0_MINOR_VERSION",
        "STAGE30_8_ALLOWED_INITIAL_FILES",
        "STAGE30_8_NEXT_RECOMMENDED_STAGE",
        "STAGE30_8_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_8_1_MINOR_VERSION",
        "STAGE30_8_2_MINOR_VERSION",
        "STAGE30_8_2_BUNDLE_SCHEMA_VERSION",
        "STAGE30_8_3_MINOR_VERSION",
        "STAGE30_8_3_INDEX_SCHEMA_VERSION",
        "STAGE30_8_3_NEXT_RECOMMENDED_STAGE",
        "STAGE30_8_3_ALLOWED_STAGE30_BASENAMES",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 8. Manifest stays constants-only + imports no PHX2 module
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
# 9. Stage 30.8.5+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_8_MINOR_RE = re.compile(r"stage_?30_8_(\d+)")


def test_inventory_admits_no_stage_30_8_5_plus_file() -> None:
    inventory = (
        tuple(STAGE30_8_4_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_8_4_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_8_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 5:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.8.4 inventory must not admit a Stage 30.8.5+ file yet; "
        f"saw {violations!r}"
    )
