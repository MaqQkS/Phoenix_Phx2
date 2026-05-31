"""Stage 30.10.3 manifest pin tests.

Pins the Stage 30.10.3 manifest constants (minor version, artifact schema
version, the three production basenames + module paths, the inventory +
scanned basenames, the test basenames, the stdlib + PHX2 import allowlists,
the artifact record / batch / sink-result field names, the fake proof expected
counts, the slice-scoped next-allowed Stage 30.9.2 RESUME token, the slice
forbidden surfaces), asserts the production + test files exist, cross-checks
the mirrored artifact schema version + field names against the Stage 30.10.3
models module, asserts the manifest stays constants-only (no def / class /
Call; imports only ``__future__`` + ``typing``; no PHX2 import), confirms the
Stage 30.10.0 / 30.10.1 / 30.10.2 constants + planned substages + the Stage
30.9.2 pause/resume relationship survive unchanged, and pins the Stage
30.10.4+ future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import PHX2.stage30.stage30_10_manifest as M
from PHX2.stage30.stage30_10_manifest import (
    STAGE30_10_1_NEXT_ALLOWED_STAGE,
    STAGE30_10_2_NEXT_ALLOWED_STAGE,
    STAGE30_10_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_10_3_ALLOWED_STAGE30_BASENAMES,
    STAGE30_10_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_10_3_ARTIFACT_BATCH_FIELDS,
    STAGE30_10_3_ARTIFACT_RECORD_FIELDS,
    STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
    STAGE30_10_3_ARTIFACT_SINK_RESULT_FIELDS,
    STAGE30_10_3_FAKE_ARTIFACT_PROOF_BASENAME,
    STAGE30_10_3_FAKE_ARTIFACT_PROOF_MODULE,
    STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED,
    STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN,
    STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED,
    STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED,
    STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_SUPPRESSED_BEFORE_RESERVATION,
    STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED,
    STAGE30_10_3_FAKE_PROOF_EXPECTED_INVALID_INPUTS,
    STAGE30_10_3_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT,
    STAGE30_10_3_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT,
    STAGE30_10_3_FORBIDDEN_SURFACES,
    STAGE30_10_3_GATE_ARTIFACT_MODELS_BASENAME,
    STAGE30_10_3_GATE_ARTIFACT_MODELS_MODULE,
    STAGE30_10_3_GATE_ARTIFACT_PROJECTOR_BASENAME,
    STAGE30_10_3_GATE_ARTIFACT_PROJECTOR_MODULE,
    STAGE30_10_3_MINOR_VERSION,
    STAGE30_10_3_NEXT_ALLOWED_STAGE,
    STAGE30_10_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_10_3_STAGE_30_9_2_RESUME_NOTE,
    STAGE30_10_3_TEST_BASENAMES,
    STAGE30_10_NEXT_ALLOWED_STAGE,
    STAGE30_10_PLANNED_SUBSTAGES,
    STAGE30_10_STAGE_30_9_2_RESUME_CONDITION,
    STAGE30_10_STAGE_30_9_2_STATUS,
    STAGE30_10_STAGE_ID,
)
from PHX2.stage30.stage30_10_3_gate_artifact_models import (
    STAGE30_10_3_ARTIFACT_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_10_3_MINOR_VERSION as MODELS_MINOR_VERSION,
    gate_artifact_batch_field_names,
    gate_artifact_record_field_names,
    gate_artifact_sink_result_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_10_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Minor version + artifact schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_10_STAGE_ID == "30.10"
    assert STAGE30_10_3_MINOR_VERSION == "30.10.3"
    assert STAGE30_10_3_MINOR_VERSION == MODELS_MINOR_VERSION


def test_artifact_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_10_3_ARTIFACT_SCHEMA_VERSION == (
        "stage30_10_v0_gate_artifact"
    )
    assert STAGE30_10_3_ARTIFACT_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_10_3_GATE_ARTIFACT_MODELS_BASENAME == (
        "stage30_10_3_gate_artifact_models.py"
    )
    assert STAGE30_10_3_GATE_ARTIFACT_PROJECTOR_BASENAME == (
        "stage30_10_3_gate_artifact_projector.py"
    )
    assert STAGE30_10_3_FAKE_ARTIFACT_PROOF_BASENAME == (
        "stage30_10_3_fake_artifact_proof.py"
    )
    assert STAGE30_10_3_GATE_ARTIFACT_MODELS_MODULE == (
        "PHX2.stage30.stage30_10_3_gate_artifact_models"
    )
    assert STAGE30_10_3_GATE_ARTIFACT_PROJECTOR_MODULE == (
        "PHX2.stage30.stage30_10_3_gate_artifact_projector"
    )
    assert STAGE30_10_3_FAKE_ARTIFACT_PROOF_MODULE == (
        "PHX2.stage30.stage30_10_3_fake_artifact_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_10_3_GATE_ARTIFACT_MODELS_BASENAME,
        STAGE30_10_3_GATE_ARTIFACT_PROJECTOR_BASENAME,
        STAGE30_10_3_FAKE_ARTIFACT_PROOF_BASENAME,
    )
    assert STAGE30_10_3_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_10_3_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_10_3_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.10.3 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_10_3_TEST_BASENAMES == (
        "test_stage_30_10_3_gate_artifact_models.py",
        "test_stage_30_10_3_gate_artifact_projector.py",
        "test_stage_30_10_3_fake_artifact_proof.py",
        "test_stage_30_10_3_boundaries.py",
        "test_stage_30_10_3_manifest.py",
    )
    for basename in STAGE30_10_3_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.10.3 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_10_3_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    for forbidden in (
        "os",
        "json",
        "pathlib",
        "sqlite3",
        "zstandard",
        "time",
        "decimal",
    ):
        assert forbidden not in STAGE30_10_3_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_10_3_ALLOWED_PHX2_IMPORTS == (
        "PHX2.stage30.stage30_10_2_pre_dispatch_gate_models",
        "PHX2.stage30.stage30_10_2_pre_dispatch_gate",
        "PHX2.stage30.stage30_10_2_fake_gate_proof",
        STAGE30_10_3_GATE_ARTIFACT_MODELS_MODULE,
        STAGE30_10_3_GATE_ARTIFACT_PROJECTOR_MODULE,
    )
    for module in STAGE30_10_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    # No Stage 30.3 / 30.4 orchestrator / suppression / transport module.
    joined = " ".join(STAGE30_10_3_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "transport", "suppress", "renderer"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Artifact field-name tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_artifact_record_fields_pinned_and_match_models() -> None:
    assert STAGE30_10_3_ARTIFACT_RECORD_FIELDS == (
        "proof_id",
        "candidate_id",
        "token_mint",
        "eligibility_decision",
        "eligibility_reason",
        "gate_decision",
        "gate_reason",
        "send_allowed",
        "dispatch_reservation_would_be_attempted",
        "suppressed_before_dispatch_reservation",
        "dispatch_failure_recorded",
        "transport_veto_used",
        "payload_refused_used",
        "created_at_utc",
    )
    assert STAGE30_10_3_ARTIFACT_RECORD_FIELDS == (
        gate_artifact_record_field_names()
    )


def test_artifact_batch_fields_pinned_and_match_models() -> None:
    assert STAGE30_10_3_ARTIFACT_BATCH_FIELDS == (
        "proof_id",
        "records",
        "candidates_seen",
        "candidates_passed",
        "candidates_skipped",
        "invalid_inputs",
        "dispatch_attempts_reserved",
        "dispatch_attempts_suppressed_before_reservation",
        "dispatch_failures_recorded",
        "transport_veto_count",
        "payload_refused_count",
        "created_at_utc",
    )
    assert STAGE30_10_3_ARTIFACT_BATCH_FIELDS == (
        gate_artifact_batch_field_names()
    )


def test_artifact_sink_result_fields_pinned_and_match_models() -> None:
    assert STAGE30_10_3_ARTIFACT_SINK_RESULT_FIELDS == (
        "proof_id",
        "records_written",
        "batch_written",
        "artifact_schema_version",
        "created_at_utc",
    )
    assert STAGE30_10_3_ARTIFACT_SINK_RESULT_FIELDS == (
        gate_artifact_sink_result_field_names()
    )


def test_no_secret_or_payload_class_field_names() -> None:
    all_fields = (
        STAGE30_10_3_ARTIFACT_RECORD_FIELDS
        + STAGE30_10_3_ARTIFACT_BATCH_FIELDS
        + STAGE30_10_3_ARTIFACT_SINK_RESULT_FIELDS
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
                f"Stage 30.10.3 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 5. Fake proof expected counts
# ---------------------------------------------------------------------------


def test_fake_proof_expected_counts_pinned() -> None:
    assert STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN == 9
    assert STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED == 3
    assert STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED == 5
    assert STAGE30_10_3_FAKE_PROOF_EXPECTED_INVALID_INPUTS == 1
    assert STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED == 3
    assert (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_SUPPRESSED_BEFORE_RESERVATION
        == 6
    )
    assert STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED == 0
    assert STAGE30_10_3_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT == 0
    assert STAGE30_10_3_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT == 0


def test_fake_proof_expected_counts_match_the_proof() -> None:
    from PHX2.stage30.stage30_10_3_fake_artifact_proof import (
        run_stage30_10_3_fake_artifact_proof,
    )

    batch = run_stage30_10_3_fake_artifact_proof()
    assert batch.candidates_seen == (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN
    )
    assert batch.candidates_passed == (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED
    )
    assert batch.candidates_skipped == (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED
    )
    assert batch.invalid_inputs == (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_INVALID_INPUTS
    )
    assert batch.dispatch_attempts_reserved == (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED
    )
    assert batch.dispatch_attempts_suppressed_before_reservation == (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_SUPPRESSED_BEFORE_RESERVATION
    )
    assert batch.dispatch_failures_recorded == (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED
    )
    assert batch.transport_veto_count == (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT
    )
    assert batch.payload_refused_count == (
        STAGE30_10_3_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT
    )


# ---------------------------------------------------------------------------
# 6. Next allowed stage + planned substages + 30.9.2 relationship
# ---------------------------------------------------------------------------


def test_next_allowed_stage_is_30_9_2_resume_and_pointers_intact() -> None:
    # Stage 30.10.3 is the final planned substage; the next allowed step is
    # the Stage 30.9.2 RESUME token, NOT a Stage 30.10.4.
    assert STAGE30_10_3_NEXT_ALLOWED_STAGE == "30.9.2_RESUME"
    assert "30.10.4" not in STAGE30_10_3_NEXT_ALLOWED_STAGE
    # The earlier slice-scoped pointers stay intact.
    assert STAGE30_10_2_NEXT_ALLOWED_STAGE == "30.10.3"
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
    # No Stage 30.10.4 is planned.
    assert "30.10.4" not in " ".join(STAGE30_10_PLANNED_SUBSTAGES)


def test_stage_30_9_2_pause_resume_unchanged() -> None:
    # Stage 30.9.2 remains paused, not abandoned; resumes only after Stage
    # 30.10 proves dip-focused eligibility.
    assert STAGE30_10_STAGE_30_9_2_STATUS == "paused, not abandoned"
    assert STAGE30_10_STAGE_30_9_2_RESUME_CONDITION == (
        "resume only after Stage 30.10 proves dip-focused eligibility"
    )


def test_stage_30_9_2_resume_note_marks_30_10_3_as_final_fake_proof() -> None:
    note = STAGE30_10_3_STAGE_30_9_2_RESUME_NOTE
    assert "Stage 30.10.3" in note
    assert "final" in note.lower()
    assert "paused, not abandoned" in note
    assert "separate" in note.lower()


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_10_3_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_10_3_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_10_3_FORBIDDEN_SURFACES)
    for token in (
        "live runtime wiring",
        "Stage 28 suppression-logic edit",
        "Stage 30.3 compact orchestrator edit",
        "Stage 30.4 compact orchestrator edit",
        "new live runner",
        "new provider",
        "new readiness gate",
        "transport-layer gate",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "live run",
        "Discord send",
        "env read",
        "filesystem write",
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
        "Stage 30.10.4+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.10.3 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the Stage 30.10.3 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_10_3_surface() -> None:
    for name in (
        "STAGE30_10_3_MINOR_VERSION",
        "STAGE30_10_3_ARTIFACT_SCHEMA_VERSION",
        "STAGE30_10_3_GATE_ARTIFACT_MODELS_BASENAME",
        "STAGE30_10_3_GATE_ARTIFACT_PROJECTOR_BASENAME",
        "STAGE30_10_3_FAKE_ARTIFACT_PROOF_BASENAME",
        "STAGE30_10_3_GATE_ARTIFACT_MODELS_MODULE",
        "STAGE30_10_3_GATE_ARTIFACT_PROJECTOR_MODULE",
        "STAGE30_10_3_FAKE_ARTIFACT_PROOF_MODULE",
        "STAGE30_10_3_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_10_3_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_10_3_TEST_BASENAMES",
        "STAGE30_10_3_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_10_3_ALLOWED_PHX2_IMPORTS",
        "STAGE30_10_3_ARTIFACT_RECORD_FIELDS",
        "STAGE30_10_3_ARTIFACT_BATCH_FIELDS",
        "STAGE30_10_3_ARTIFACT_SINK_RESULT_FIELDS",
        "STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN",
        "STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED",
        "STAGE30_10_3_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED",
        "STAGE30_10_3_FAKE_PROOF_EXPECTED_INVALID_INPUTS",
        "STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED",
        (
            "STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_"
            "SUPPRESSED_BEFORE_RESERVATION"
        ),
        "STAGE30_10_3_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED",
        "STAGE30_10_3_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT",
        "STAGE30_10_3_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT",
        "STAGE30_10_3_NEXT_ALLOWED_STAGE",
        "STAGE30_10_3_NEXT_ALLOWED_STAGE_TITLE",
        "STAGE30_10_3_FORBIDDEN_SURFACES",
        "STAGE30_10_3_STAGE_30_9_2_RESUME_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_10_constants_still_present() -> None:
    # The Stage 30.10.3 manifest edit is purely additive: the Stage 30.10.0 /
    # 30.10.1 / 30.10.2 constants survive.
    for name in (
        "STAGE30_10_STAGE_ID",
        "STAGE30_10_0_MINOR_VERSION",
        "STAGE30_10_ELIGIBILITY_DECISIONS",
        "STAGE30_10_PLANNED_SUBSTAGES",
        "STAGE30_10_FORBIDDEN_SURFACES",
        "STAGE30_10_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_10_1_MINOR_VERSION",
        "STAGE30_10_1_NEXT_ALLOWED_STAGE",
        "STAGE30_10_2_MINOR_VERSION",
        "STAGE30_10_2_GATE_DECISIONS",
        "STAGE30_10_2_NEXT_ALLOWED_STAGE",
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
# 10. Stage 30.10.4+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_10_MINOR_RE = re.compile(r"stage_?30_10_(\d+)")


def test_inventory_admits_no_stage_30_10_4_plus_file() -> None:
    inventory = (
        tuple(STAGE30_10_3_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_10_3_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_10_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 4:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.10.3 inventory must not admit a Stage 30.10.4+ file yet; "
        f"saw {violations!r}"
    )
