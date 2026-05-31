"""Stage 30.10.1 manifest pin tests.

Pins the Stage 30.10.1 manifest constants (minor version, the two production
basenames + module paths, the inventory + scanned basenames, the test
basenames, the stdlib + PHX2 import allowlists, the eligibility reason closed
set + send-allowed reason, the slice-scoped next allowed stage, the slice
forbidden surfaces), asserts the production + test files exist, cross-checks
the mirrored decision / reason closed sets against the Stage 30.10.1 models
module, asserts the manifest stays constants-only (no def / class / Call;
imports only ``__future__`` + ``typing``; no PHX2 import), confirms the
Stage 30.10.0 spec-lock constants + planned substages survive unchanged, and
pins the Stage 30.10.2+ future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import PHX2.stage30.stage30_10_manifest as M
from PHX2.stage30.stage30_10_manifest import (
    STAGE30_10_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_10_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_10_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME,
    STAGE30_10_1_ELIGIBILITY_CLASSIFIER_MODULE,
    STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME,
    STAGE30_10_1_ELIGIBILITY_MODELS_MODULE,
    STAGE30_10_1_ELIGIBILITY_REASONS,
    STAGE30_10_1_FORBIDDEN_SURFACES,
    STAGE30_10_1_MINOR_VERSION,
    STAGE30_10_1_NEXT_ALLOWED_STAGE,
    STAGE30_10_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_10_1_SEND_ALLOWED_REASON,
    STAGE30_10_1_TEST_BASENAMES,
    STAGE30_10_ELIGIBILITY_DECISIONS,
    STAGE30_10_NEXT_ALLOWED_STAGE,
    STAGE30_10_PLANNED_SUBSTAGES,
    STAGE30_10_SEND_ALLOWED_DECISION,
    STAGE30_10_STAGE_ID,
)
from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    REASON_TIER_ALLOWED,
    STAGE30_10_1_ELIGIBILITY_DECISIONS as MODELS_DECISIONS,
    STAGE30_10_1_ELIGIBILITY_REASONS as MODELS_REASONS,
    STAGE30_10_1_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_10_1_SEND_ALLOWED_DECISION as MODELS_SEND_ALLOWED_DECISION,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_10_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Minor version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_10_STAGE_ID == "30.10"
    assert STAGE30_10_1_MINOR_VERSION == "30.10.1"
    assert STAGE30_10_1_MINOR_VERSION == MODELS_MINOR_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME == (
        "stage30_10_1_tier_dip_eligibility_models.py"
    )
    assert STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME == (
        "stage30_10_1_tier_dip_eligibility_classifier.py"
    )
    assert STAGE30_10_1_ELIGIBILITY_MODELS_MODULE == (
        "PHX2.stage30.stage30_10_1_tier_dip_eligibility_models"
    )
    assert STAGE30_10_1_ELIGIBILITY_CLASSIFIER_MODULE == (
        "PHX2.stage30.stage30_10_1_tier_dip_eligibility_classifier"
    )


def test_allowed_and_scanned_basenames_are_the_two_modules() -> None:
    expected = (
        STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME,
        STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME,
    )
    assert STAGE30_10_1_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_10_1_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_10_1_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.10.1 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_10_1_TEST_BASENAMES == (
        "test_stage_30_10_1_tier_dip_eligibility_models.py",
        "test_stage_30_10_1_tier_dip_eligibility_classifier.py",
        "test_stage_30_10_1_boundaries.py",
        "test_stage_30_10_1_manifest.py",
    )
    for basename in STAGE30_10_1_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.10.1 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_10_1_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
        "re",
    )
    for forbidden in ("os", "json", "pathlib", "sqlite3", "zstandard", "time"):
        assert forbidden not in STAGE30_10_1_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_the_models_sibling_only() -> None:
    assert STAGE30_10_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_10_1_ELIGIBILITY_MODELS_MODULE,
    )
    for module in STAGE30_10_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")


# ---------------------------------------------------------------------------
# 4. Decision + reason closed sets (mirrored from models)
# ---------------------------------------------------------------------------


def test_decision_closed_set_matches_models_and_family() -> None:
    # The Stage 30.10.1 models mirror the family decision closed set BY VALUE.
    assert MODELS_DECISIONS == STAGE30_10_ELIGIBILITY_DECISIONS
    assert MODELS_SEND_ALLOWED_DECISION == STAGE30_10_SEND_ALLOWED_DECISION
    assert MODELS_SEND_ALLOWED_DECISION == "ELIGIBLE_DIP"


def test_reason_closed_set_pinned_and_matches_models() -> None:
    assert STAGE30_10_1_ELIGIBILITY_REASONS == (
        "TIER_ALLOWED",
        "TIER_NOT_ALLOWED",
        "TIER_UNKNOWN",
        "TIER_NOT_APPLICABLE",
        "MISSING_ATH",
        "MISSING_MIGRATION",
        "MISSING_DRAWDOWN",
        "MISSING_MARKET_CONTEXT",
        "MISSING_CURRENT_MARKET_CAP",
        "PRE_MIGRATION_ATH_NOT_ALLOWED",
        "INVALID_CANDIDATE_ID",
        "INVALID_TOKEN_MINT",
        "INVALID_CREATED_AT_UTC",
        "INVALID_POLICY",
    )
    assert STAGE30_10_1_ELIGIBILITY_REASONS == MODELS_REASONS


def test_send_allowed_reason_pinned_and_matches_models() -> None:
    assert STAGE30_10_1_SEND_ALLOWED_REASON == "TIER_ALLOWED"
    assert STAGE30_10_1_SEND_ALLOWED_REASON == REASON_TIER_ALLOWED


# ---------------------------------------------------------------------------
# 5. Next allowed stage + planned substages
# ---------------------------------------------------------------------------


def test_next_allowed_stage_is_30_10_2_and_family_pointer_intact() -> None:
    assert STAGE30_10_1_NEXT_ALLOWED_STAGE == "30.10.2"
    # The Stage 30.10.0 family pointer stays pinned at 30.10.1 (the slice the
    # spec-lock backs); the 30.10.1-scoped pointer names the next slice.
    assert STAGE30_10_NEXT_ALLOWED_STAGE == "30.10.1"


def test_planned_substages_unchanged_30_10_0_through_30_10_3() -> None:
    assert STAGE30_10_PLANNED_SUBSTAGES == (
        "30.10.0",
        "30.10.1",
        "30.10.2",
        "30.10.3",
    )


# ---------------------------------------------------------------------------
# 6. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_10_1_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_10_1_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_10_1_FORBIDDEN_SURFACES)
    for token in (
        "live runtime wiring",
        "Stage 28 suppression-logic edit",
        "Stage 30.3 compact orchestrator edit",
        "Stage 30.4 compact orchestrator edit",
        "new live runner",
        "new provider",
        "new readiness gate",
        "live run",
        "Discord send",
        "env read",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "zstd dependency",
        "compression implementation",
        "default storage root",
        "public routing",
        "subscriber routing",
        "paid tiers",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "Stage 25/27/28/29 production import",
        "commit",
        "tag",
        "push",
        "Stage 30.10.2+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.10.1 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 7. Manifest __all__ exports the Stage 30.10.1 surface + 30.10.0 survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_10_1_surface() -> None:
    for name in (
        "STAGE30_10_1_MINOR_VERSION",
        "STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME",
        "STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME",
        "STAGE30_10_1_ELIGIBILITY_MODELS_MODULE",
        "STAGE30_10_1_ELIGIBILITY_CLASSIFIER_MODULE",
        "STAGE30_10_1_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_10_1_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_10_1_TEST_BASENAMES",
        "STAGE30_10_1_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_10_1_ALLOWED_PHX2_IMPORTS",
        "STAGE30_10_1_ELIGIBILITY_REASONS",
        "STAGE30_10_1_SEND_ALLOWED_REASON",
        "STAGE30_10_1_NEXT_ALLOWED_STAGE",
        "STAGE30_10_1_NEXT_ALLOWED_STAGE_TITLE",
        "STAGE30_10_1_FORBIDDEN_SURFACES",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_10_0_constants_still_present() -> None:
    # The Stage 30.10.1 manifest edit is purely additive: the Stage 30.10.0
    # spec-lock constants survive.
    for name in (
        "STAGE30_10_STAGE_ID",
        "STAGE30_10_0_MINOR_VERSION",
        "STAGE30_10_0_SPEC_VERSION",
        "STAGE30_10_ALLOWED_INITIAL_FILES",
        "STAGE30_10_NEXT_ALLOWED_STAGE",
        "STAGE30_10_ELIGIBILITY_DECISIONS",
        "STAGE30_10_SEND_ALLOWED_DECISION",
        "STAGE30_10_PLANNED_SUBSTAGES",
        "STAGE30_10_FORBIDDEN_SURFACES",
        "STAGE30_10_FORBIDDEN_TEXT_NEEDLES",
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
        ), "Stage 30.10 manifest must be constants-only (no def / class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.10 manifest must be constants-only (no Call)"
        )
    allowed_import_roots = {"__future__", "typing"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.10 manifest may import only __future__ / typing; "
                f"saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.10 manifest may import only __future__ / "
                    f"typing; saw {alias.name!r}"
                )


def test_manifest_imports_no_phx2_module() -> None:
    tree = ast.parse(_manifest_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("PHX2"), (
                f"Stage 30.10 manifest imports PHX2 module {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("PHX2"), (
                    f"Stage 30.10 manifest imports PHX2 module {alias.name!r}"
                )


# ---------------------------------------------------------------------------
# 9. Stage 30.10.2+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_10_MINOR_RE = re.compile(r"stage_?30_10_(\d+)")


def test_inventory_admits_no_stage_30_10_2_plus_file() -> None:
    inventory = (
        tuple(STAGE30_10_1_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_10_1_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_10_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 2:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.10.1 inventory must not admit a Stage 30.10.2+ file yet; "
        f"saw {violations!r}"
    )
