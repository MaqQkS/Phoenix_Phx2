"""Stage 30.9.2_RESUME manifest pin tests.

Pins the Stage 30.9.2 manifest constants (minor version, resume id, prior
stage, required HEAD sha, resume proof schema version, required dip-gate
stack, the three production basenames + module paths, the inventory +
scanned basenames, the test basenames, the stdlib + PHX2 import allowlists,
the resume plan / record / summary field names, the planning-only gating
flags, the fake proof expected counts, the resume status + note + the
explicit operator-authorized next-allowed step, the slice forbidden
surfaces), asserts the production + test files exist, cross-checks the
mirrored schema version + field names + gate stack against the Stage 30.9.2
models, cross-checks the required HEAD sha against the resume plan, confirms
the earlier Stage 30.9.0 / 30.9.1 constants survive, asserts the manifest
stays constants-only (no def / class / Call; imports only ``__future__`` +
``typing``; no PHX2 import), and pins the Stage 30.9.3+ / Stage 30.10.4+ /
Stage 31 future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import PHX2.stage30.stage30_9_manifest as M
from PHX2.stage30.stage30_9_manifest import (
    STAGE30_9_2_ALLOWED_PHX2_IMPORTS,
    STAGE30_9_2_ALLOWED_STAGE30_BASENAMES,
    STAGE30_9_2_ALLOWED_STDLIB_IMPORTS,
    STAGE30_9_2_CANDIDATE_PROOF_RECORD_FIELDS,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_DISCORD_SEND_ALLOWED,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_SUPPRESSED_BEFORE_RESERVATION,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_LIVE_ALLOWED,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_PROVIDER_CALL_ALLOWED,
    STAGE30_9_2_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT,
    STAGE30_9_2_FORBIDDEN_SURFACES,
    STAGE30_9_2_GATE_STACK_REQUIRED,
    STAGE30_9_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_9_2_MINOR_VERSION,
    STAGE30_9_2_NEXT_ALLOWED_STEP,
    STAGE30_9_2_NEXT_ALLOWED_STEP_TITLE,
    STAGE30_9_2_PRIOR_STAGE,
    STAGE30_9_2_REQUIRED_HEAD_SHA,
    STAGE30_9_2_RESUME_FAKE_PROOF_BASENAME,
    STAGE30_9_2_RESUME_FAKE_PROOF_MODULE,
    STAGE30_9_2_RESUME_ID,
    STAGE30_9_2_RESUME_MODELS_BASENAME,
    STAGE30_9_2_RESUME_MODELS_MODULE,
    STAGE30_9_2_RESUME_NOTE,
    STAGE30_9_2_RESUME_PLAN_BASENAME,
    STAGE30_9_2_RESUME_PLAN_FIELDS,
    STAGE30_9_2_RESUME_PLAN_MODULE,
    STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION,
    STAGE30_9_2_RESUME_PROOF_SUMMARY_FIELDS,
    STAGE30_9_2_RESUME_STATUS,
    STAGE30_9_2_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_9_2_TEST_BASENAMES,
    STAGE30_9_NEXT_ALLOWED_STAGE,
    STAGE30_9_STAGE_ID,
)
from PHX2.stage30.stage30_9_2_resume_dip_filtered_live_models import (
    STAGE30_9_2_GATE_STACK_REQUIRED as MODELS_GATE_STACK,
    STAGE30_9_2_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_9_2_PRIOR_STAGE as MODELS_PRIOR_STAGE,
    STAGE30_9_2_RESUME_ID as MODELS_RESUME_ID,
    STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    candidate_proof_record_field_names,
    resume_plan_field_names,
    resume_proof_summary_field_names,
)
from PHX2.stage30.stage30_9_2_resume_dip_filtered_live_plan import (
    STAGE30_9_2_REQUIRED_HEAD_SHA as PLAN_REQUIRED_HEAD_SHA,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
MANIFEST_PATH: Path = STAGE30_ROOT / "stage30_9_manifest.py"


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Versions + resume identity (mirrored from models / plan)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_9_STAGE_ID == "30.9"
    assert STAGE30_9_2_MINOR_VERSION == "30.9.2"
    assert STAGE30_9_2_MINOR_VERSION == MODELS_MINOR_VERSION


def test_resume_id_pinned_and_matches_models() -> None:
    assert STAGE30_9_2_RESUME_ID == "30.9.2_RESUME"
    assert STAGE30_9_2_RESUME_ID == MODELS_RESUME_ID


def test_prior_stage_pinned_and_matches_models() -> None:
    assert STAGE30_9_2_PRIOR_STAGE == "30.10.3"
    assert STAGE30_9_2_PRIOR_STAGE == MODELS_PRIOR_STAGE


def test_required_head_sha_pinned_and_matches_plan() -> None:
    assert STAGE30_9_2_REQUIRED_HEAD_SHA == (
        "e35e54b69668814d2ab8c096855f682c68ada8ab"
    )
    assert STAGE30_9_2_REQUIRED_HEAD_SHA == PLAN_REQUIRED_HEAD_SHA


def test_resume_proof_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION == (
        "stage30_9_2_v0_dip_filtered_resume_proof"
    )
    assert STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


def test_required_gate_stack_pinned_and_matches_models() -> None:
    assert STAGE30_9_2_GATE_STACK_REQUIRED == (
        "30.10.1 offline tier-dip eligibility classifier",
        "30.10.2 optional pre-dispatch tier-dip gate",
        "30.10.3 gate artifact projection",
    )
    assert STAGE30_9_2_GATE_STACK_REQUIRED == MODELS_GATE_STACK


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_9_2_RESUME_MODELS_BASENAME == (
        "stage30_9_2_resume_dip_filtered_live_models.py"
    )
    assert STAGE30_9_2_RESUME_PLAN_BASENAME == (
        "stage30_9_2_resume_dip_filtered_live_plan.py"
    )
    assert STAGE30_9_2_RESUME_FAKE_PROOF_BASENAME == (
        "stage30_9_2_resume_fake_proof.py"
    )
    assert STAGE30_9_2_RESUME_MODELS_MODULE == (
        "PHX2.stage30.stage30_9_2_resume_dip_filtered_live_models"
    )
    assert STAGE30_9_2_RESUME_PLAN_MODULE == (
        "PHX2.stage30.stage30_9_2_resume_dip_filtered_live_plan"
    )
    assert STAGE30_9_2_RESUME_FAKE_PROOF_MODULE == (
        "PHX2.stage30.stage30_9_2_resume_fake_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_9_2_RESUME_MODELS_BASENAME,
        STAGE30_9_2_RESUME_PLAN_BASENAME,
        STAGE30_9_2_RESUME_FAKE_PROOF_BASENAME,
    )
    assert STAGE30_9_2_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_9_2_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_9_2_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.9.2 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_9_2_TEST_BASENAMES == (
        "test_stage_30_9_2_resume_dip_filtered_live_models.py",
        "test_stage_30_9_2_resume_dip_filtered_live_plan.py",
        "test_stage_30_9_2_resume_fake_proof.py",
        "test_stage_30_9_2_resume_boundaries.py",
        "test_stage_30_9_2_resume_manifest.py",
    )
    for basename in STAGE30_9_2_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.9.2 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_9_2_ALLOWED_STDLIB_IMPORTS == (
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
        assert forbidden not in STAGE30_9_2_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_9_2_ALLOWED_PHX2_IMPORTS == (
        STAGE30_9_2_RESUME_MODELS_MODULE,
        STAGE30_9_2_RESUME_PLAN_MODULE,
        "PHX2.stage30.stage30_10_3_fake_artifact_proof",
        "PHX2.stage30.stage30_10_3_gate_artifact_models",
    )
    for module in STAGE30_9_2_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    # No Stage 30.3 / 30.4 orchestrator / suppression / transport module.
    joined = " ".join(STAGE30_9_2_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "transport", "suppress", "renderer"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Field-name tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_resume_plan_fields_pinned_and_match_models() -> None:
    assert STAGE30_9_2_RESUME_PLAN_FIELDS == (
        "resume_id",
        "required_head_sha",
        "prior_stage",
        "gate_stack_required",
        "live_allowed",
        "dispatch_allowed",
        "env_read_allowed",
        "provider_call_allowed",
        "discord_send_allowed",
        "created_at_utc",
    )
    assert STAGE30_9_2_RESUME_PLAN_FIELDS == resume_plan_field_names()


def test_candidate_proof_record_fields_pinned_and_match_models() -> None:
    assert STAGE30_9_2_CANDIDATE_PROOF_RECORD_FIELDS == (
        "candidate_id",
        "token_mint",
        "eligibility_decision",
        "eligibility_reason",
        "gate_decision",
        "gate_reason",
        "artifact_schema_version",
        "dispatch_reservation_would_be_attempted",
        "suppressed_before_dispatch_reservation",
        "dispatch_failure_recorded",
        "transport_veto_used",
        "payload_refused_used",
        "created_at_utc",
    )
    assert STAGE30_9_2_CANDIDATE_PROOF_RECORD_FIELDS == (
        candidate_proof_record_field_names()
    )


def test_resume_proof_summary_fields_pinned_and_match_models() -> None:
    assert STAGE30_9_2_RESUME_PROOF_SUMMARY_FIELDS == (
        "resume_id",
        "candidates_seen",
        "candidates_passed",
        "candidates_skipped",
        "invalid_inputs",
        "dispatch_attempts_reserved",
        "dispatch_attempts_suppressed_before_reservation",
        "dispatch_failures_recorded",
        "transport_veto_count",
        "payload_refused_count",
        "live_allowed",
        "provider_call_allowed",
        "discord_send_allowed",
        "created_at_utc",
    )
    assert STAGE30_9_2_RESUME_PROOF_SUMMARY_FIELDS == (
        resume_proof_summary_field_names()
    )


def test_no_secret_or_payload_class_field_names() -> None:
    all_fields = (
        STAGE30_9_2_RESUME_PLAN_FIELDS
        + STAGE30_9_2_CANDIDATE_PROOF_RECORD_FIELDS
        + STAGE30_9_2_RESUME_PROOF_SUMMARY_FIELDS
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "webhook",
            "api_key",
            "bearer",
            "secret",
            "raw_payload",
            "getenv",
            "environ",
            "url",
            "host",
        ):
            assert forbidden not in lower, (
                f"Stage 30.9.2 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 5. Fake proof expected counts + planning gating flags
# ---------------------------------------------------------------------------


def test_fake_proof_expected_counts_pinned() -> None:
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN == 9
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED == 3
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED == 5
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS == 1
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED == 3
    assert (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_SUPPRESSED_BEFORE_RESERVATION
        == 6
    )
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED == 0
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT == 0
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT == 0
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_LIVE_ALLOWED is False
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_PROVIDER_CALL_ALLOWED is False
    assert STAGE30_9_2_FAKE_PROOF_EXPECTED_DISCORD_SEND_ALLOWED is False


def test_planning_gating_flags_all_false() -> None:
    assert M.STAGE30_9_2_PLANNING_LIVE_ALLOWED is False
    assert M.STAGE30_9_2_PLANNING_DISPATCH_ALLOWED is False
    assert M.STAGE30_9_2_PLANNING_ENV_READ_ALLOWED is False
    assert M.STAGE30_9_2_PLANNING_PROVIDER_CALL_ALLOWED is False
    assert M.STAGE30_9_2_PLANNING_DISCORD_SEND_ALLOWED is False


def test_fake_proof_expected_counts_match_the_proof() -> None:
    from PHX2.stage30.stage30_9_2_resume_fake_proof import (
        run_stage30_9_2_resume_fake_proof,
    )

    summary = run_stage30_9_2_resume_fake_proof()
    assert summary.candidates_seen == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN
    )
    assert summary.candidates_passed == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED
    )
    assert summary.candidates_skipped == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED
    )
    assert summary.invalid_inputs == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS
    )
    assert summary.dispatch_attempts_reserved == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED
    )
    assert summary.dispatch_attempts_suppressed_before_reservation == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_SUPPRESSED_BEFORE_RESERVATION
    )
    assert summary.dispatch_failures_recorded == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED
    )
    assert summary.transport_veto_count == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT
    )
    assert summary.payload_refused_count == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT
    )
    assert summary.live_allowed == STAGE30_9_2_FAKE_PROOF_EXPECTED_LIVE_ALLOWED
    assert summary.provider_call_allowed == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_PROVIDER_CALL_ALLOWED
    )
    assert summary.discord_send_allowed == (
        STAGE30_9_2_FAKE_PROOF_EXPECTED_DISCORD_SEND_ALLOWED
    )


# ---------------------------------------------------------------------------
# 6. Resume status + note + next allowed step (operator-authorized live)
# ---------------------------------------------------------------------------


def test_resume_status_is_planning_fake_proof_only() -> None:
    assert STAGE30_9_2_RESUME_STATUS == (
        "unpaused for dip-filtered planning / fake proof only"
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_9_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


def test_resume_note_marks_30_10_3_as_final_fake_proof_before_resume() -> None:
    note = STAGE30_9_2_RESUME_NOTE
    assert "Stage 30.10.3" in note
    assert "final" in note.lower()
    assert "operator-authorized" in note.lower()
    assert "separate" in note.lower()


def test_next_allowed_step_is_controlled_operator_authorized_ceremony() -> None:
    # The next allowed step is a controlled, explicitly operator-authorized
    # live ceremony -- NOT an automatic live execution and NOT a Stage 30.10.4.
    assert STAGE30_9_2_NEXT_ALLOWED_STEP == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    lower = STAGE30_9_2_NEXT_ALLOWED_STEP_TITLE.lower()
    assert "operator-authorized" in lower
    assert "live ceremony" in lower
    assert "automatic live execution" in lower
    assert "30.10.4" in STAGE30_9_2_NEXT_ALLOWED_STEP_TITLE


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_9_2_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_9_2_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_9_2_FORBIDDEN_SURFACES)
    for token in (
        "live run",
        "live provider call",
        "Discord send",
        "env read",
        "real provider key use",
        "dispatch reservation",
        "filesystem write",
        "transport-layer gate",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "runtime orchestrator wiring",
        "Stage 28 suppression-logic edit",
        "Stage 30.3 compact orchestrator edit",
        "Stage 30.4 compact orchestrator edit",
        "new live runner",
        "new provider",
        "new readiness gate",
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
        "automatic live execution",
        "Stage 30.10.4+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.9.2 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the Stage 30.9.2 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_9_2_surface() -> None:
    for name in (
        "STAGE30_9_2_MINOR_VERSION",
        "STAGE30_9_2_RESUME_ID",
        "STAGE30_9_2_PRIOR_STAGE",
        "STAGE30_9_2_REQUIRED_HEAD_SHA",
        "STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION",
        "STAGE30_9_2_GATE_STACK_REQUIRED",
        "STAGE30_9_2_RESUME_MODELS_BASENAME",
        "STAGE30_9_2_RESUME_PLAN_BASENAME",
        "STAGE30_9_2_RESUME_FAKE_PROOF_BASENAME",
        "STAGE30_9_2_RESUME_MODELS_MODULE",
        "STAGE30_9_2_RESUME_PLAN_MODULE",
        "STAGE30_9_2_RESUME_FAKE_PROOF_MODULE",
        "STAGE30_9_2_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_9_2_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_9_2_TEST_BASENAMES",
        "STAGE30_9_2_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_9_2_ALLOWED_PHX2_IMPORTS",
        "STAGE30_9_2_RESUME_PLAN_FIELDS",
        "STAGE30_9_2_CANDIDATE_PROOF_RECORD_FIELDS",
        "STAGE30_9_2_RESUME_PROOF_SUMMARY_FIELDS",
        "STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN",
        "STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED",
        "STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED",
        "STAGE30_9_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS",
        "STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED",
        (
            "STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_"
            "SUPPRESSED_BEFORE_RESERVATION"
        ),
        "STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED",
        "STAGE30_9_2_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT",
        "STAGE30_9_2_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT",
        "STAGE30_9_2_RESUME_STATUS",
        "STAGE30_9_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_9_2_RESUME_NOTE",
        "STAGE30_9_2_NEXT_ALLOWED_STEP",
        "STAGE30_9_2_NEXT_ALLOWED_STEP_TITLE",
        "STAGE30_9_2_FORBIDDEN_SURFACES",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_9_constants_still_present() -> None:
    # The Stage 30.9.2 manifest edit is purely additive: the Stage 30.9.0 /
    # 30.9.1 constants survive.
    for name in (
        "STAGE30_9_STAGE_ID",
        "STAGE30_9_0_MINOR_VERSION",
        "STAGE30_9_PLANNED_SUBSTAGES",
        "STAGE30_9_NEXT_ALLOWED_STAGE",
        "STAGE30_9_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_9_1_MINOR_VERSION",
        "STAGE30_9_1_NEXT_ALLOWED_STAGE",
        "STAGE30_9_1_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_9_1_TEST_BASENAMES",
    ):
        assert name in M.__all__


def test_family_pointer_unchanged_and_planned_substages_intact() -> None:
    # The Stage 30.9.0 family pointer stays pinned at 30.9.1; the planned
    # substage tuple still stops at 30.9.2 (the resume is that substage).
    assert STAGE30_9_NEXT_ALLOWED_STAGE == "30.9.1"
    assert M.STAGE30_9_PLANNED_SUBSTAGES == ("30.9.0", "30.9.1", "30.9.2")


# ---------------------------------------------------------------------------
# 9. Manifest stays constants-only + imports no PHX2 module
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
                    f"Stage 30.9 manifest imports PHX2 module {alias.name!r}"
                )


# ---------------------------------------------------------------------------
# 10. Stage 30.9.3+ / Stage 30.10.4+ / Stage 31 future guard
# ---------------------------------------------------------------------------


_STAGE_30_9_MINOR_RE = re.compile(r"stage_?30_9_(\d+)")
_STAGE_30_10_MINOR_RE = re.compile(r"stage_?30_10_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_9_3_plus_file() -> None:
    inventory = (
        tuple(STAGE30_9_2_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_9_2_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_9_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 3:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.9.2 inventory must not admit a Stage 30.9.3+ file yet; "
        f"saw {violations!r}"
    )


def test_inventory_admits_no_stage_30_10_4_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_9_2_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_9_2_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_10_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 3, (
                "Stage 30.9.2 inventory must not admit a Stage 30.10.4+ file; "
                f"offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.9.2 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )
