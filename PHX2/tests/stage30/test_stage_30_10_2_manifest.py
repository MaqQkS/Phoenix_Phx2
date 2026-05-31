"""Stage 30.10.2 manifest pin tests.

Pins the Stage 30.10.2 manifest constants (minor version, the three
production basenames + module paths, the inventory + scanned basenames, the
test basenames, the stdlib + PHX2 import allowlists, the gate-decision /
gate-reason closed sets + pass tokens, the gate input / record / proof-summary
field names, the slice-scoped next allowed stage, the slice forbidden
surfaces), asserts the production + test files exist, cross-checks the
mirrored gate decision / reason closed sets against the Stage 30.10.2 gate
models module, asserts the manifest stays constants-only (no def / class /
Call; imports only ``__future__`` + ``typing``; no PHX2 import), confirms the
Stage 30.10.0 / 30.10.1 constants + planned substages + the Stage 30.9.2
pause/resume relationship survive unchanged, and pins the Stage 30.10.3+
future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import PHX2.stage30.stage30_10_manifest as M
from PHX2.stage30.stage30_10_manifest import (
    STAGE30_10_1_NEXT_ALLOWED_STAGE,
    STAGE30_10_2_ALLOWED_PHX2_IMPORTS,
    STAGE30_10_2_ALLOWED_STAGE30_BASENAMES,
    STAGE30_10_2_ALLOWED_STDLIB_IMPORTS,
    STAGE30_10_2_FAKE_GATE_PROOF_BASENAME,
    STAGE30_10_2_FAKE_GATE_PROOF_MODULE,
    STAGE30_10_2_FORBIDDEN_SURFACES,
    STAGE30_10_2_GATE_DECISIONS,
    STAGE30_10_2_GATE_INPUT_FIELDS,
    STAGE30_10_2_GATE_PASS_DECISION,
    STAGE30_10_2_GATE_REASONS,
    STAGE30_10_2_GATE_RECORD_FIELDS,
    STAGE30_10_2_MINOR_VERSION,
    STAGE30_10_2_NEXT_ALLOWED_STAGE,
    STAGE30_10_2_PRE_DISPATCH_GATE_BASENAME,
    STAGE30_10_2_PRE_DISPATCH_GATE_MODELS_BASENAME,
    STAGE30_10_2_PRE_DISPATCH_GATE_MODELS_MODULE,
    STAGE30_10_2_PRE_DISPATCH_GATE_MODULE,
    STAGE30_10_2_PROOF_SUMMARY_FIELDS,
    STAGE30_10_2_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_10_2_TEST_BASENAMES,
    STAGE30_10_NEXT_ALLOWED_STAGE,
    STAGE30_10_PLANNED_SUBSTAGES,
    STAGE30_10_STAGE_30_9_2_RESUME_CONDITION,
    STAGE30_10_STAGE_30_9_2_STATUS,
    STAGE30_10_STAGE_ID,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    STAGE30_10_2_GATE_DECISIONS as MODELS_GATE_DECISIONS,
    STAGE30_10_2_GATE_PASS_DECISION as MODELS_GATE_PASS_DECISION,
    STAGE30_10_2_GATE_REASONS as MODELS_GATE_REASONS,
    STAGE30_10_2_MINOR_VERSION as MODELS_MINOR_VERSION,
    gate_input_field_names,
    gate_record_field_names,
    proof_summary_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_10_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Minor version (mirrored from gate models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_10_STAGE_ID == "30.10"
    assert STAGE30_10_2_MINOR_VERSION == "30.10.2"
    assert STAGE30_10_2_MINOR_VERSION == MODELS_MINOR_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_10_2_PRE_DISPATCH_GATE_MODELS_BASENAME == (
        "stage30_10_2_pre_dispatch_gate_models.py"
    )
    assert STAGE30_10_2_PRE_DISPATCH_GATE_BASENAME == (
        "stage30_10_2_pre_dispatch_gate.py"
    )
    assert STAGE30_10_2_FAKE_GATE_PROOF_BASENAME == (
        "stage30_10_2_fake_gate_proof.py"
    )
    assert STAGE30_10_2_PRE_DISPATCH_GATE_MODELS_MODULE == (
        "PHX2.stage30.stage30_10_2_pre_dispatch_gate_models"
    )
    assert STAGE30_10_2_PRE_DISPATCH_GATE_MODULE == (
        "PHX2.stage30.stage30_10_2_pre_dispatch_gate"
    )
    assert STAGE30_10_2_FAKE_GATE_PROOF_MODULE == (
        "PHX2.stage30.stage30_10_2_fake_gate_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_10_2_PRE_DISPATCH_GATE_MODELS_BASENAME,
        STAGE30_10_2_PRE_DISPATCH_GATE_BASENAME,
        STAGE30_10_2_FAKE_GATE_PROOF_BASENAME,
    )
    assert STAGE30_10_2_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_10_2_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_10_2_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.10.2 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_10_2_TEST_BASENAMES == (
        "test_stage_30_10_2_pre_dispatch_gate_models.py",
        "test_stage_30_10_2_pre_dispatch_gate.py",
        "test_stage_30_10_2_fake_gate_proof.py",
        "test_stage_30_10_2_boundaries.py",
        "test_stage_30_10_2_manifest.py",
    )
    for basename in STAGE30_10_2_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.10.2 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_10_2_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    for forbidden in ("os", "json", "pathlib", "sqlite3", "zstandard", "time"):
        assert forbidden not in STAGE30_10_2_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_10_2_ALLOWED_PHX2_IMPORTS == (
        "PHX2.stage30.stage30_10_1_tier_dip_eligibility_models",
        "PHX2.stage30.stage30_10_1_tier_dip_eligibility_classifier",
        STAGE30_10_2_PRE_DISPATCH_GATE_MODELS_MODULE,
        STAGE30_10_2_PRE_DISPATCH_GATE_MODULE,
    )
    for module in STAGE30_10_2_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    # No Stage 30.3 / 30.4 orchestrator / suppression module is allowlisted.
    joined = " ".join(STAGE30_10_2_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "transport", "suppress", "renderer"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Gate decision + reason closed sets (mirrored from gate models)
# ---------------------------------------------------------------------------


def test_gate_decisions_closed_set_pinned_and_matches_models() -> None:
    assert STAGE30_10_2_GATE_DECISIONS == (
        "PASS_TO_DISPATCH",
        "SKIP_BEFORE_DISPATCH",
        "INVALID_INPUT",
    )
    assert STAGE30_10_2_GATE_DECISIONS == MODELS_GATE_DECISIONS
    assert STAGE30_10_2_GATE_PASS_DECISION == "PASS_TO_DISPATCH"
    assert STAGE30_10_2_GATE_PASS_DECISION == MODELS_GATE_PASS_DECISION


def test_gate_reasons_closed_set_pinned_and_matches_models() -> None:
    assert STAGE30_10_2_GATE_REASONS == (
        "ELIGIBLE_DIP",
        "NOT_DIP",
        "INVALID_GATE_INPUT",
    )
    assert STAGE30_10_2_GATE_REASONS == MODELS_GATE_REASONS


def test_no_payload_refused_in_gate_closed_sets() -> None:
    joined = " ".join(STAGE30_10_2_GATE_DECISIONS + STAGE30_10_2_GATE_REASONS)
    assert "PAYLOAD_REFUSED" not in joined
    assert "REFUSED" not in joined


# ---------------------------------------------------------------------------
# 5. Field-name tuples (mirrored from gate models)
# ---------------------------------------------------------------------------


def test_gate_input_fields_pinned_and_match_models() -> None:
    assert STAGE30_10_2_GATE_INPUT_FIELDS == (
        "candidate_id",
        "token_mint",
        "eligibility_input",
        "candidate_ref",
        "created_at_utc",
    )
    assert STAGE30_10_2_GATE_INPUT_FIELDS == gate_input_field_names()


def test_gate_record_fields_pinned_and_match_models() -> None:
    assert STAGE30_10_2_GATE_RECORD_FIELDS == (
        "candidate_id",
        "token_mint",
        "eligibility_decision",
        "eligibility_reason",
        "send_allowed",
        "gate_decision",
        "gate_reason",
        "created_at_utc",
    )
    assert STAGE30_10_2_GATE_RECORD_FIELDS == gate_record_field_names()


def test_proof_summary_fields_pinned_and_match_models() -> None:
    assert STAGE30_10_2_PROOF_SUMMARY_FIELDS == (
        "candidates_seen",
        "candidates_passed",
        "candidates_skipped",
        "invalid_inputs",
        "dispatch_attempts_reserved",
        "dispatch_attempts_suppressed_before_reservation",
        "created_at_utc",
    )
    assert STAGE30_10_2_PROOF_SUMMARY_FIELDS == proof_summary_field_names()


# ---------------------------------------------------------------------------
# 6. Next allowed stage + planned substages + 30.9.2 relationship
# ---------------------------------------------------------------------------


def test_next_allowed_stage_is_30_10_3_and_pointers_intact() -> None:
    assert STAGE30_10_2_NEXT_ALLOWED_STAGE == "30.10.3"
    # The Stage 30.10.1-scoped pointer still names 30.10.2 (this slice).
    assert STAGE30_10_1_NEXT_ALLOWED_STAGE == "30.10.2"
    # The Stage 30.10.0 family pointer stays pinned at 30.10.1.
    assert STAGE30_10_NEXT_ALLOWED_STAGE == "30.10.1"


def test_planned_substages_unchanged_30_10_0_through_30_10_3() -> None:
    assert STAGE30_10_PLANNED_SUBSTAGES == (
        "30.10.0",
        "30.10.1",
        "30.10.2",
        "30.10.3",
    )


def test_stage_30_9_2_pause_resume_unchanged() -> None:
    # Stage 30.9.2 remains paused, not abandoned; resumes only after Stage
    # 30.10 proves dip-focused eligibility.
    assert STAGE30_10_STAGE_30_9_2_STATUS == "paused, not abandoned"
    assert STAGE30_10_STAGE_30_9_2_RESUME_CONDITION == (
        "resume only after Stage 30.10 proves dip-focused eligibility"
    )


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_10_2_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_10_2_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_10_2_FORBIDDEN_SURFACES)
    for token in (
        "live runtime wiring",
        "Stage 28 suppression-logic edit",
        "Stage 30.3 compact orchestrator edit",
        "Stage 30.4 compact orchestrator edit",
        "new live runner",
        "new provider",
        "new readiness gate",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "live run",
        "Discord send",
        "env read",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
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
        "Stage 30.10.3+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.10.2 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the Stage 30.10.2 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_10_2_surface() -> None:
    for name in (
        "STAGE30_10_2_MINOR_VERSION",
        "STAGE30_10_2_PRE_DISPATCH_GATE_MODELS_BASENAME",
        "STAGE30_10_2_PRE_DISPATCH_GATE_BASENAME",
        "STAGE30_10_2_FAKE_GATE_PROOF_BASENAME",
        "STAGE30_10_2_PRE_DISPATCH_GATE_MODELS_MODULE",
        "STAGE30_10_2_PRE_DISPATCH_GATE_MODULE",
        "STAGE30_10_2_FAKE_GATE_PROOF_MODULE",
        "STAGE30_10_2_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_10_2_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_10_2_TEST_BASENAMES",
        "STAGE30_10_2_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_10_2_ALLOWED_PHX2_IMPORTS",
        "STAGE30_10_2_GATE_DECISIONS",
        "STAGE30_10_2_GATE_PASS_DECISION",
        "STAGE30_10_2_GATE_REASONS",
        "STAGE30_10_2_GATE_INPUT_FIELDS",
        "STAGE30_10_2_GATE_RECORD_FIELDS",
        "STAGE30_10_2_PROOF_SUMMARY_FIELDS",
        "STAGE30_10_2_NEXT_ALLOWED_STAGE",
        "STAGE30_10_2_NEXT_ALLOWED_STAGE_TITLE",
        "STAGE30_10_2_FORBIDDEN_SURFACES",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_10_0_and_30_10_1_constants_still_present() -> None:
    # The Stage 30.10.2 manifest edit is purely additive: the Stage 30.10.0
    # spec-lock + Stage 30.10.1 constants survive.
    for name in (
        "STAGE30_10_STAGE_ID",
        "STAGE30_10_0_MINOR_VERSION",
        "STAGE30_10_ELIGIBILITY_DECISIONS",
        "STAGE30_10_SEND_ALLOWED_DECISION",
        "STAGE30_10_PLANNED_SUBSTAGES",
        "STAGE30_10_FORBIDDEN_SURFACES",
        "STAGE30_10_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_10_1_MINOR_VERSION",
        "STAGE30_10_1_ELIGIBILITY_REASONS",
        "STAGE30_10_1_NEXT_ALLOWED_STAGE",
        "STAGE30_10_STAGE_30_9_2_STATUS",
        "STAGE30_10_STAGE_30_9_2_RESUME_CONDITION",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 9. Manifest stays constants-only + imports no PHX2 module
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
# 10. Stage 30.10.3+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_10_MINOR_RE = re.compile(r"stage_?30_10_(\d+)")


def test_inventory_admits_no_stage_30_10_3_plus_file() -> None:
    inventory = (
        tuple(STAGE30_10_2_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_10_2_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_10_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 3:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.10.2 inventory must not admit a Stage 30.10.3+ file yet; "
        f"saw {violations!r}"
    )
