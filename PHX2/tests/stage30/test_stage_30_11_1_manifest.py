"""Stage 30.11.1 manifest pin tests.

Pins the Stage 30.11.1 manifest constants (minor version, bridge schema
version, the three production basenames + module paths, the committed Stage
30.9.3 sibling module paths, the inventory + scanned basenames, the test
basenames, the stdlib + PHX2 import allowlists, the bridge decision / reason
tokens, the candidate snapshot / bridge result / proof summary field names, the
fake proof expected counts, the slice-scoped next-allowed Stage 30.11.2 token,
the slice forbidden surfaces, the operator-auth live-ceremony note), asserts
the production + test files exist, cross-checks the mirrored schema version +
decision / reason tokens + field names against the Stage 30.11.1 models module,
cross-checks the fake proof expected counts against the proof, asserts the
manifest stays constants-only (no def / class / Call; imports only
``__future__`` + ``typing``; no PHX2 import), confirms the Stage 30.11.0
constants + planned substages + family next-allowed pointer survive unchanged,
and pins the Stage 30.11.2+ future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_1_BRIDGE_BASENAME,
    STAGE30_11_1_BRIDGE_DECISIONS,
    STAGE30_11_1_BRIDGE_MODELS_BASENAME,
    STAGE30_11_1_BRIDGE_MODELS_MODULE,
    STAGE30_11_1_BRIDGE_MODULE,
    STAGE30_11_1_BRIDGE_PASS_DECISION,
    STAGE30_11_1_BRIDGE_PROOF_SUMMARY_FIELDS,
    STAGE30_11_1_BRIDGE_REASONS,
    STAGE30_11_1_BRIDGE_RESULT_FIELDS,
    STAGE30_11_1_BRIDGE_SCHEMA_VERSION,
    STAGE30_11_1_CANDIDATE_SNAPSHOT_FIELDS,
    STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME,
    STAGE30_11_1_FAKE_BRIDGE_PROOF_MODULE,
    STAGE30_11_1_FAKE_PROOF_EXPECTED_BRIDGED,
    STAGE30_11_1_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_1_FAKE_PROOF_EXPECTED_INVALID_INPUTS,
    STAGE30_11_1_FAKE_PROOF_EXPECTED_SKIPPED_MISSING_CONTEXT,
    STAGE30_11_1_FORBIDDEN_SURFACES,
    STAGE30_11_1_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_1_MINOR_VERSION,
    STAGE30_11_1_NEXT_ALLOWED_STAGE,
    STAGE30_11_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE,
    STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_11_1_TEST_BASENAMES,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_PLANNED_SUBSTAGES,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    STAGE30_11_1_BRIDGE_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_1_BRIDGE_REASONS as MODELS_REASONS,
    STAGE30_11_1_BRIDGE_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_1_MINOR_VERSION as MODELS_MINOR_VERSION,
    bridge_proof_summary_field_names,
    bridge_result_field_names,
    candidate_snapshot_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_11_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Minor version + bridge schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_1_MINOR_VERSION == "30.11.1"
    assert STAGE30_11_1_MINOR_VERSION == MODELS_MINOR_VERSION


def test_bridge_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_1_BRIDGE_SCHEMA_VERSION == (
        "stage30_11_1_v0_live_candidate_bridge"
    )
    assert STAGE30_11_1_BRIDGE_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_1_BRIDGE_MODELS_BASENAME == (
        "stage30_11_1_live_candidate_bridge_models.py"
    )
    assert STAGE30_11_1_BRIDGE_BASENAME == (
        "stage30_11_1_live_candidate_bridge.py"
    )
    assert STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME == (
        "stage30_11_1_fake_bridge_proof.py"
    )
    assert STAGE30_11_1_BRIDGE_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_1_live_candidate_bridge_models"
    )
    assert STAGE30_11_1_BRIDGE_MODULE == (
        "PHX2.stage30.stage30_11_1_live_candidate_bridge"
    )
    assert STAGE30_11_1_FAKE_BRIDGE_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_1_fake_bridge_proof"
    )


def test_committed_gate_sibling_modules_pinned() -> None:
    assert STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE == (
        "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models"
    )
    assert STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_1_BRIDGE_MODELS_BASENAME,
        STAGE30_11_1_BRIDGE_BASENAME,
        STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME,
    )
    assert STAGE30_11_1_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_1_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_1_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.1 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_1_TEST_BASENAMES == (
        "test_stage_30_11_1_live_candidate_bridge_models.py",
        "test_stage_30_11_1_live_candidate_bridge.py",
        "test_stage_30_11_1_fake_bridge_proof.py",
        "test_stage_30_11_1_boundaries.py",
        "test_stage_30_11_1_manifest.py",
    )
    for basename in STAGE30_11_1_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.1 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_1_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    for forbidden in ("os", "json", "pathlib", "sqlite3", "zstandard", "time"):
        assert forbidden not in STAGE30_11_1_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_11_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_1_BRIDGE_MODELS_MODULE,
        STAGE30_11_1_BRIDGE_MODULE,
        STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE,
        STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE,
    )
    for module in STAGE30_11_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    # No runtime orchestrator / transport / suppression / renderer module.
    joined = " ".join(STAGE30_11_1_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "transport", "suppress", "renderer"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Bridge decisions + reasons (mirrored from models)
# ---------------------------------------------------------------------------


def test_bridge_decisions_pinned_and_match_models() -> None:
    assert STAGE30_11_1_BRIDGE_DECISIONS == (
        "BRIDGED_TO_LIVE_GATE_INPUT",
        "SKIPPED_MISSING_REQUIRED_CONTEXT",
        "INVALID_BRIDGE_INPUT",
    )
    assert STAGE30_11_1_BRIDGE_PASS_DECISION == "BRIDGED_TO_LIVE_GATE_INPUT"
    assert STAGE30_11_1_BRIDGE_DECISIONS == MODELS_DECISIONS


def test_bridge_reasons_pinned_and_match_models() -> None:
    assert STAGE30_11_1_BRIDGE_REASONS == (
        "READY_FOR_DIP_GATE",
        "MISSING_REQUIRED_CONTEXT",
        "INVALID_FIELD_SHAPE",
    )
    assert STAGE30_11_1_BRIDGE_REASONS == MODELS_REASONS


# ---------------------------------------------------------------------------
# 5. Field-name tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_candidate_snapshot_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_1_CANDIDATE_SNAPSHOT_FIELDS == (
        "candidate_id",
        "token_mint",
        "pair_type",
        "tier_hint",
        "drawdown_from_ath",
        "migration_status",
        "ath_status",
        "market_context_status",
        "current_market_cap_usd",
        "post_migration_ath_verified",
        "source_ref",
        "created_at_utc",
    )
    assert STAGE30_11_1_CANDIDATE_SNAPSHOT_FIELDS == (
        candidate_snapshot_field_names()
    )


def test_bridge_result_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_1_BRIDGE_RESULT_FIELDS == (
        "candidate_id",
        "token_mint",
        "bridge_decision",
        "bridge_reason",
        "live_gate_input",
        "created_at_utc",
    )
    assert STAGE30_11_1_BRIDGE_RESULT_FIELDS == bridge_result_field_names()


def test_bridge_proof_summary_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_1_BRIDGE_PROOF_SUMMARY_FIELDS == (
        "candidates_seen",
        "bridged",
        "skipped_missing_context",
        "invalid_inputs",
        "created_at_utc",
    )
    assert STAGE30_11_1_BRIDGE_PROOF_SUMMARY_FIELDS == (
        bridge_proof_summary_field_names()
    )


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        STAGE30_11_1_CANDIDATE_SNAPSHOT_FIELDS
        + STAGE30_11_1_BRIDGE_RESULT_FIELDS
        + STAGE30_11_1_BRIDGE_PROOF_SUMMARY_FIELDS
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "webhook",
            "api_key",
            "bearer",
            "authorization",
            "secret",
            "raw_payload",
            "getenv",
            "environ",
            "url",
            "host",
        ):
            assert forbidden not in lower, (
                f"Stage 30.11.1 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. Fake proof expected counts
# ---------------------------------------------------------------------------


def test_fake_proof_expected_counts_pinned() -> None:
    assert STAGE30_11_1_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN == 5
    assert STAGE30_11_1_FAKE_PROOF_EXPECTED_BRIDGED == 2
    assert STAGE30_11_1_FAKE_PROOF_EXPECTED_SKIPPED_MISSING_CONTEXT == 2
    assert STAGE30_11_1_FAKE_PROOF_EXPECTED_INVALID_INPUTS == 1
    # The counts partition the stream exactly.
    assert (
        STAGE30_11_1_FAKE_PROOF_EXPECTED_BRIDGED
        + STAGE30_11_1_FAKE_PROOF_EXPECTED_SKIPPED_MISSING_CONTEXT
        + STAGE30_11_1_FAKE_PROOF_EXPECTED_INVALID_INPUTS
        == STAGE30_11_1_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN
    )


def test_fake_proof_expected_counts_match_the_proof() -> None:
    from PHX2.stage30.stage30_11_1_fake_bridge_proof import (
        run_stage30_11_1_fake_bridge_proof,
    )

    _results, summary = run_stage30_11_1_fake_bridge_proof()
    assert summary.candidates_seen == (
        STAGE30_11_1_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN
    )
    assert summary.bridged == STAGE30_11_1_FAKE_PROOF_EXPECTED_BRIDGED
    assert summary.skipped_missing_context == (
        STAGE30_11_1_FAKE_PROOF_EXPECTED_SKIPPED_MISSING_CONTEXT
    )
    assert summary.invalid_inputs == (
        STAGE30_11_1_FAKE_PROOF_EXPECTED_INVALID_INPUTS
    )


# ---------------------------------------------------------------------------
# 7. Next allowed stage + family pointer + planned substages unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_stage_is_30_11_2_and_family_pointer_intact() -> None:
    # The 30.11.1-scoped pointer advances to 30.11.2; the Stage 30.11.0 family
    # pointer stays pinned at 30.11.1 (mirrors the Stage 30.9 / 30.10 manifest
    # convention).
    assert STAGE30_11_1_NEXT_ALLOWED_STAGE == "30.11.2"
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


def test_planned_substages_unchanged_30_11_0_through_30_11_4() -> None:
    assert STAGE30_11_PLANNED_SUBSTAGES == (
        "30.11.0",
        "30.11.1",
        "30.11.2",
        "30.11.3",
        "30.11.4",
    )
    # No Stage 30.12 / Stage 31 token sneaks into the planned sequence.
    joined = " ".join(STAGE30_11_PLANNED_SUBSTAGES)
    assert "30.12" not in joined
    assert "31" not in joined


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_1_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 8. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_1_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_1_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_1_FORBIDDEN_SURFACES)
    for token in (
        "runtime gate seam",
        "real dispatch sink",
        "dispatch reservation",
        "dispatch sink call",
        "runtime session loop",
        "live run",
        "live provider call",
        "Discord send",
        "env read",
        "new live runner",
        "new provider",
        "new readiness gate",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "Stage 28 suppression-logic edit",
        "Stage 29 live provider / session edit",
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
        "commit",
        "tag",
        "push",
        "Stage 30.11.2+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.1 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 9. Manifest __all__ exports the Stage 30.11.1 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_1_surface() -> None:
    for name in (
        "STAGE30_11_1_MINOR_VERSION",
        "STAGE30_11_1_BRIDGE_SCHEMA_VERSION",
        "STAGE30_11_1_BRIDGE_MODELS_BASENAME",
        "STAGE30_11_1_BRIDGE_BASENAME",
        "STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME",
        "STAGE30_11_1_BRIDGE_MODELS_MODULE",
        "STAGE30_11_1_BRIDGE_MODULE",
        "STAGE30_11_1_FAKE_BRIDGE_PROOF_MODULE",
        "STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE",
        "STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE",
        "STAGE30_11_1_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_1_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_1_TEST_BASENAMES",
        "STAGE30_11_1_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_1_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_1_BRIDGE_DECISIONS",
        "STAGE30_11_1_BRIDGE_PASS_DECISION",
        "STAGE30_11_1_BRIDGE_REASONS",
        "STAGE30_11_1_CANDIDATE_SNAPSHOT_FIELDS",
        "STAGE30_11_1_BRIDGE_RESULT_FIELDS",
        "STAGE30_11_1_BRIDGE_PROOF_SUMMARY_FIELDS",
        "STAGE30_11_1_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN",
        "STAGE30_11_1_FAKE_PROOF_EXPECTED_BRIDGED",
        "STAGE30_11_1_FAKE_PROOF_EXPECTED_SKIPPED_MISSING_CONTEXT",
        "STAGE30_11_1_FAKE_PROOF_EXPECTED_INVALID_INPUTS",
        "STAGE30_11_1_NEXT_ALLOWED_STAGE",
        "STAGE30_11_1_NEXT_ALLOWED_STAGE_TITLE",
        "STAGE30_11_1_FORBIDDEN_SURFACES",
        "STAGE30_11_1_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_1_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_constants_still_present() -> None:
    # The Stage 30.11.1 manifest edit is purely additive: the Stage 30.11.0
    # spec-lock constants survive.
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_0_SPEC_VERSION",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_GATE_DECISIONS",
        "STAGE30_11_GATE_PLACEMENT",
        "STAGE30_11_ONLY_PASS_SEND_RULE",
        "STAGE30_11_RESULT_COUNTER_AXES",
        "STAGE30_11_FORBIDDEN_SURFACES",
        "STAGE30_11_FORBIDDEN_RUNTIME_IMPORTS",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 10. Manifest stays constants-only + imports no PHX2 module
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only() -> None:
    tree = ast.parse(_manifest_text())
    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), "Stage 30.11 manifest must be constants-only (no def / class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.11 manifest must be constants-only (no Call)"
        )
    allowed_import_roots = {"__future__", "typing"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.11 manifest may import only __future__ / typing; "
                f"saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.11 manifest may import only __future__ / "
                    f"typing; saw {alias.name!r}"
                )


def test_manifest_imports_no_phx2_module() -> None:
    tree = ast.parse(_manifest_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("PHX2"), (
                f"Stage 30.11 manifest imports PHX2 module {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("PHX2"), (
                    f"Stage 30.11 manifest imports PHX2 module {alias.name!r}"
                )


# ---------------------------------------------------------------------------
# 11. Stage 30.11.2+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_2_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_1_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_1_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 2:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.1 inventory must not admit a Stage 30.11.2+ file yet; "
        f"saw {violations!r}"
    )
