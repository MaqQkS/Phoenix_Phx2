"""Stage 30.9.1 manifest pin tests.

Pins the Stage 30.9.1 artifact-bridge manifest constants (minor version,
bridge proof schema version, scenario names, the bridge status / reason
closed sets, the private webhook identity allowlist, the author-verified
expected counts, the four production basenames + module paths, the
inventory + scanned basenames, the test basenames, the stdlib + PHX2
import allowlists, the forbidden surfaces, the next allowed stage),
asserts the production + test files exist, cross-checks the mirrored
constants against the Stage 30.9.1 bridge models (including the two
scenarios' expected counts), asserts the manifest stays constants-only (no
def / class / Call; imports only ``__future__`` + ``typing``; no PHX2
import), asserts the Stage 30.9.0 spec-lock constants survive, and pins the
Stage 30.9.2+ future guard.

Doc / constants only. No live call, no env read, no actual-disk read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import PHX2.stage30.stage30_9_manifest as M
from PHX2.stage30.stage30_9_manifest import (
    STAGE30_9_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_9_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_9_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME,
    STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE,
    STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME,
    STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_MODULE,
    STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME,
    STAGE30_9_1_ARTIFACT_PROJECTOR_MODULE,
    STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION,
    STAGE30_9_1_BRIDGE_REASON_VALUES,
    STAGE30_9_1_BRIDGE_STATUS_VALUES,
    STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME,
    STAGE30_9_1_CAPTURE_TRANSPORT_MODULE,
    STAGE30_9_1_DEFAULT_EXPECTED_DUPLICATE_SUPPRESSED,
    STAGE30_9_1_DEFAULT_EXPECTED_INVALID_SUPPRESSED,
    STAGE30_9_1_DEFAULT_EXPECTED_PING_COUNT,
    STAGE30_9_1_DEFAULT_EXPECTED_RETAINED,
    STAGE30_9_1_DEFAULT_SCENARIO_NAME,
    STAGE30_9_1_FORBIDDEN_SURFACES,
    STAGE30_9_1_MINOR_VERSION,
    STAGE30_9_1_MISMATCH_EXPECTED_DUPLICATE_SUPPRESSED,
    STAGE30_9_1_MISMATCH_EXPECTED_INVALID_SUPPRESSED,
    STAGE30_9_1_MISMATCH_EXPECTED_PING_COUNT,
    STAGE30_9_1_MISMATCH_EXPECTED_RETAINED,
    STAGE30_9_1_MISMATCH_SCENARIO_NAME,
    STAGE30_9_1_NEXT_ALLOWED_STAGE,
    STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES,
    STAGE30_9_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_9_1_TEST_BASENAMES,
    STAGE30_9_NEXT_ALLOWED_STAGE,
    STAGE30_9_STAGE_ID,
)
from PHX2.stage30.stage30_9_artifact_bridge_models import (
    STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION as MODELS_BRIDGE_SCHEMA,
    STAGE30_9_1_BRIDGE_REASON_VALUES as MODELS_REASON_VALUES,
    STAGE30_9_1_BRIDGE_STATUS_VALUES as MODELS_STATUS_VALUES,
    STAGE30_9_1_DEFAULT_SCENARIO_NAME as MODELS_DEFAULT_NAME,
    STAGE30_9_1_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_9_1_MISMATCH_SCENARIO_NAME as MODELS_MISMATCH_NAME,
    STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES as MODELS_PRIVATE_IDENTITIES,
    default_bridge_scenario,
    mismatch_bridge_scenario,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_9_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Versions + schema identity + scenario names (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_9_STAGE_ID == "30.9"
    assert STAGE30_9_1_MINOR_VERSION == "30.9.1"
    assert STAGE30_9_1_MINOR_VERSION == MODELS_MINOR_VERSION


def test_bridge_proof_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION == (
        "stage30_9_v0_compact_artifact_bridge_proof"
    )
    assert STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION == MODELS_BRIDGE_SCHEMA


def test_scenario_names_pinned_and_match_models() -> None:
    assert STAGE30_9_1_DEFAULT_SCENARIO_NAME == (
        "stage30_9_1_default_dedupe_bridge"
    )
    assert STAGE30_9_1_MISMATCH_SCENARIO_NAME == (
        "stage30_9_1_mismatch_dedupe_bridge"
    )
    assert STAGE30_9_1_DEFAULT_SCENARIO_NAME == MODELS_DEFAULT_NAME
    assert STAGE30_9_1_MISMATCH_SCENARIO_NAME == MODELS_MISMATCH_NAME


# ---------------------------------------------------------------------------
# 2. Closed-set status / reason tokens (mirrored from models)
# ---------------------------------------------------------------------------


def test_bridge_status_values_pinned_and_match_models() -> None:
    assert STAGE30_9_1_BRIDGE_STATUS_VALUES == (
        "CAPTURED",
        "PROJECTED",
        "WRITTEN_AND_INDEXED",
        "INVALID_INPUT",
        "PROJECT_FAILED",
        "WRITE_FAILED",
        "READ_FAILED",
        "INDEX_FAILED",
    )
    assert STAGE30_9_1_BRIDGE_STATUS_VALUES == MODELS_STATUS_VALUES


def test_bridge_reason_values_pinned_and_match_models() -> None:
    assert STAGE30_9_1_BRIDGE_REASON_VALUES == (
        "NONE",
        "MISSING_RUN_ID",
        "MISSING_SESSION_ID",
        "MISSING_PING_ID",
        "MISSING_CANDIDATE_ID",
        "MISSING_TOKEN_MINT",
        "MISSING_DEDUPE_KEY",
        "MISSING_COMPACT_BODY",
        "MISSING_CAPTURE_INDEX",
        "COUNT_MISMATCH",
        "AMBIGUOUS_JOIN",
        "NON_PRIVATE_WEBHOOK",
        "WRITER_REJECTED",
        "READER_REJECTED",
        "INDEX_REJECTED",
    )
    assert STAGE30_9_1_BRIDGE_REASON_VALUES == MODELS_REASON_VALUES


def test_private_webhook_identities_pinned_and_match_models() -> None:
    assert STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES == (
        "PRIVATE_OPERATOR_WEBHOOK",
    )
    assert STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES == MODELS_PRIVATE_IDENTITIES


# ---------------------------------------------------------------------------
# 3. Expected counts (mirrored from models + the live scenarios)
# ---------------------------------------------------------------------------


def test_default_expected_counts_pinned_and_match_scenario() -> None:
    assert STAGE30_9_1_DEFAULT_EXPECTED_PING_COUNT == 3
    assert STAGE30_9_1_DEFAULT_EXPECTED_RETAINED == 2
    assert STAGE30_9_1_DEFAULT_EXPECTED_DUPLICATE_SUPPRESSED == 1
    assert STAGE30_9_1_DEFAULT_EXPECTED_INVALID_SUPPRESSED == 0
    scenario = default_bridge_scenario()
    assert scenario.expected_ping_count == (
        STAGE30_9_1_DEFAULT_EXPECTED_PING_COUNT
    )
    assert scenario.expected_retained == STAGE30_9_1_DEFAULT_EXPECTED_RETAINED
    assert scenario.expected_duplicate_suppressed == (
        STAGE30_9_1_DEFAULT_EXPECTED_DUPLICATE_SUPPRESSED
    )
    assert scenario.expected_invalid_suppressed == (
        STAGE30_9_1_DEFAULT_EXPECTED_INVALID_SUPPRESSED
    )
    # Internal consistency: retained + duplicate + invalid == ping count.
    assert (
        STAGE30_9_1_DEFAULT_EXPECTED_RETAINED
        + STAGE30_9_1_DEFAULT_EXPECTED_DUPLICATE_SUPPRESSED
        + STAGE30_9_1_DEFAULT_EXPECTED_INVALID_SUPPRESSED
        == STAGE30_9_1_DEFAULT_EXPECTED_PING_COUNT
    )


def test_mismatch_expected_counts_pinned_and_match_scenario() -> None:
    assert STAGE30_9_1_MISMATCH_EXPECTED_PING_COUNT == 4
    assert STAGE30_9_1_MISMATCH_EXPECTED_RETAINED == 2
    assert STAGE30_9_1_MISMATCH_EXPECTED_DUPLICATE_SUPPRESSED == 1
    assert STAGE30_9_1_MISMATCH_EXPECTED_INVALID_SUPPRESSED == 1
    scenario = mismatch_bridge_scenario()
    assert scenario.expected_ping_count == (
        STAGE30_9_1_MISMATCH_EXPECTED_PING_COUNT
    )
    assert scenario.expected_retained == STAGE30_9_1_MISMATCH_EXPECTED_RETAINED
    assert scenario.expected_duplicate_suppressed == (
        STAGE30_9_1_MISMATCH_EXPECTED_DUPLICATE_SUPPRESSED
    )
    assert scenario.expected_invalid_suppressed == (
        STAGE30_9_1_MISMATCH_EXPECTED_INVALID_SUPPRESSED
    )
    assert (
        STAGE30_9_1_MISMATCH_EXPECTED_RETAINED
        + STAGE30_9_1_MISMATCH_EXPECTED_DUPLICATE_SUPPRESSED
        + STAGE30_9_1_MISMATCH_EXPECTED_INVALID_SUPPRESSED
        == STAGE30_9_1_MISMATCH_EXPECTED_PING_COUNT
    )


# ---------------------------------------------------------------------------
# 4. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME == (
        "stage30_9_artifact_bridge_models.py"
    )
    assert STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME == (
        "stage30_9_capture_transport.py"
    )
    assert STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME == (
        "stage30_9_artifact_projector.py"
    )
    assert STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME == (
        "stage30_9_artifact_bridge_proof.py"
    )
    assert STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE == (
        "PHX2.stage30.stage30_9_artifact_bridge_models"
    )
    assert STAGE30_9_1_CAPTURE_TRANSPORT_MODULE == (
        "PHX2.stage30.stage30_9_capture_transport"
    )
    assert STAGE30_9_1_ARTIFACT_PROJECTOR_MODULE == (
        "PHX2.stage30.stage30_9_artifact_projector"
    )
    assert STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_MODULE == (
        "PHX2.stage30.stage30_9_artifact_bridge_proof"
    )


def test_allowed_and_scanned_basenames_are_the_four_modules() -> None:
    expected = (
        STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME,
        STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME,
        STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME,
        STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME,
    )
    assert STAGE30_9_1_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_9_1_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_9_1_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.9.1 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_9_1_TEST_BASENAMES == (
        "test_stage_30_9_1_artifact_bridge_models.py",
        "test_stage_30_9_1_capture_transport.py",
        "test_stage_30_9_1_artifact_projector.py",
        "test_stage_30_9_1_artifact_bridge_proof.py",
        "test_stage_30_9_1_boundaries.py",
        "test_stage_30_9_1_manifest.py",
    )
    for basename in STAGE30_9_1_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.9.1 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 5. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_9_1_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    assert "os" not in STAGE30_9_1_ALLOWED_STDLIB_IMPORTS
    assert "json" not in STAGE30_9_1_ALLOWED_STDLIB_IMPORTS
    assert "pathlib" not in STAGE30_9_1_ALLOWED_STDLIB_IMPORTS
    assert "sqlite3" not in STAGE30_9_1_ALLOWED_STDLIB_IMPORTS
    assert "zstandard" not in STAGE30_9_1_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_the_bridge_and_stage_30_8_siblings() -> None:
    assert STAGE30_9_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE,
        STAGE30_9_1_ARTIFACT_PROJECTOR_MODULE,
        "PHX2.stage30.stage30_8_artifact_models",
        "PHX2.stage30.stage30_8_temp_artifact_writer",
        "PHX2.stage30.stage30_8_session_bundle_reader",
        "PHX2.stage30.stage30_8_session_index_builder",
        "PHX2.stage30.stage30_8_session_index_models",
    )
    # Every allowlisted PHX2 import is a Stage 30 sibling; none is a Stage
    # 21-29 (incl. Stage 28 / 29.5) production module.
    for module in STAGE30_9_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")


# ---------------------------------------------------------------------------
# 6. Forbidden surfaces + next allowed stage
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_9_1_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_9_1_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_9_1_FORBIDDEN_SURFACES)
    for token in (
        "live provider call",
        "real Discord send",
        "default storage root",
        "per-ping Stage 30.8 write",
        "new live runner",
        "new readiness gate",
        "wall-clock daemon",
        "background service",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "zstd dependency",
        "compression implementation",
        "env read",
        "public routing",
        "subscriber routing",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "Stage 30.8 implementation edit",
        "Stage 25/27/28/29 production import",
        "Stage 29.5 production import",
        "commit",
        "tag",
        "push",
        "Stage 30.9.2+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.9.1 forbidden surfaces must name {token!r}"
        )


def test_next_allowed_stage_is_30_9_2_and_family_pointer_intact() -> None:
    assert STAGE30_9_1_NEXT_ALLOWED_STAGE == "30.9.2"
    # The Stage 30.9.0 family pointer stays pinned at 30.9.1 (the slice this
    # manifest now backs); the 30.9.1-scoped pointer names the next slice.
    assert STAGE30_9_NEXT_ALLOWED_STAGE == "30.9.1"


# ---------------------------------------------------------------------------
# 7. Manifest __all__ exports the Stage 30.9.1 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_surface() -> None:
    for name in (
        "STAGE30_9_1_MINOR_VERSION",
        "STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION",
        "STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME",
        "STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME",
        "STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME",
        "STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME",
        "STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE",
        "STAGE30_9_1_CAPTURE_TRANSPORT_MODULE",
        "STAGE30_9_1_ARTIFACT_PROJECTOR_MODULE",
        "STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_MODULE",
        "STAGE30_9_1_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_9_1_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_9_1_TEST_BASENAMES",
        "STAGE30_9_1_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_9_1_ALLOWED_PHX2_IMPORTS",
        "STAGE30_9_1_BRIDGE_STATUS_VALUES",
        "STAGE30_9_1_BRIDGE_REASON_VALUES",
        "STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES",
        "STAGE30_9_1_FORBIDDEN_SURFACES",
        "STAGE30_9_1_NEXT_ALLOWED_STAGE",
        "STAGE30_9_1_NEXT_ALLOWED_STAGE_TITLE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_9_0_constants_still_present() -> None:
    # The Stage 30.9.1 manifest edit is purely additive: the Stage 30.9.0
    # spec-lock constants the 30.9.0 pin test imports must remain.
    for name in (
        "STAGE30_9_STAGE_ID",
        "STAGE30_9_0_MINOR_VERSION",
        "STAGE30_9_0_SPEC_VERSION",
        "STAGE30_9_ALLOWED_INITIAL_FILES",
        "STAGE30_9_NEXT_ALLOWED_STAGE",
        "STAGE30_9_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_9_PLANNED_SUBSTAGES",
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
        ), "Stage 30.9 manifest must be constants-only (no def / class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.9 manifest must be constants-only (no Call)"
        )
    allowed_import_roots = {"__future__", "typing"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.9 manifest may import only __future__ / typing; "
                f"saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.9 manifest may import only __future__ / "
                    f"typing; saw {alias.name!r}"
                )


def test_manifest_imports_no_phx2_module() -> None:
    tree = ast.parse(_manifest_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("PHX2"), (
                f"Stage 30.9 manifest imports PHX2 module {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("PHX2"), (
                    f"Stage 30.9 manifest imports PHX2 module "
                    f"{alias.name!r}"
                )


# ---------------------------------------------------------------------------
# 9. Stage 30.9.2+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_9_MINOR_RE = re.compile(r"stage_?30_9_(\d+)")


def test_inventory_admits_no_stage_30_9_2_plus_file() -> None:
    inventory = (
        tuple(STAGE30_9_1_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_9_1_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_9_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 2:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.9.1 inventory must not admit a Stage 30.9.2+ file yet; "
        f"saw {violations!r}"
    )


def test_stage_30_9_1_production_basenames_carry_no_minor_token() -> None:
    # The Stage 30.9.1 production basenames carry no minor digit after
    # ``stage30_9_`` (so they are admitted purely by the explicit allowlist,
    # never by a minor-token match).
    for basename in STAGE30_9_1_ALLOWED_STAGE30_BASENAMES:
        assert _STAGE_30_9_MINOR_RE.search(basename.lower()) is None
