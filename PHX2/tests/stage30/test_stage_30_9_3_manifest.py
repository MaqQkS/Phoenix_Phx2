"""Stage 30.9.3 dip-filtered live dispatch integration manifest pin tests.

Pins the Stage 30.9.3 manifest constants (minor version, prior stage,
integration schema version, required dip-gate stack, gate decisions, the four
production basenames + module paths, the inventory + scanned basenames, the
test basenames, the stdlib + PHX2 import allowlists, the live gate input /
decision / integration result field names, the fake-proof expected counts, the
operator-auth gate + integration note + next-allowed step, the slice forbidden
surfaces), asserts the production + test files exist, cross-checks the mirrored
schema version + field names against the Stage 30.9.3 models, cross-checks the
fake-proof expected counts against the proof, confirms the earlier Stage 30.9
constants survive, and pins the Stage 30.9.4+ future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_9_manifest as M
from PHX2.stage30.stage30_9_manifest import (
    STAGE30_9_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_9_3_ALLOWED_STAGE30_BASENAMES,
    STAGE30_9_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_9_3_DISPATCH_ALLOWED_GATE_DECISION,
    STAGE30_9_3_FAKE_PROOF_DIP_PRESENT_DISPATCHES,
    STAGE30_9_3_FAKE_PROOF_DISPATCH_FAILURES_RECORDED,
    STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_PASSED,
    STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SEEN,
    STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SKIPPED,
    STAGE30_9_3_FAKE_PROOF_FULL_DISPATCH_ATTEMPTS_RESERVED,
    STAGE30_9_3_FAKE_PROOF_FULL_INVALID_INPUTS,
    STAGE30_9_3_FAKE_PROOF_FULL_WOULD_SEND_PRIVATE_DISCORD,
    STAGE30_9_3_FAKE_PROOF_NO_DIP_CANDIDATES_SKIPPED,
    STAGE30_9_3_FAKE_PROOF_NO_DIP_DISPATCHES,
    STAGE30_9_3_FAKE_PROOF_NO_DIP_INVALID_INPUTS,
    STAGE30_9_3_FAKE_PROOF_PAYLOAD_REFUSED_COUNT,
    STAGE30_9_3_FAKE_PROOF_TRANSPORT_VETO_COUNT,
    STAGE30_9_3_FORBIDDEN_SURFACES,
    STAGE30_9_3_GATE_ADAPTER_BASENAME,
    STAGE30_9_3_GATE_ADAPTER_MODULE,
    STAGE30_9_3_GATE_DECISIONS,
    STAGE30_9_3_GATE_MODELS_BASENAME,
    STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME,
    STAGE30_9_3_GATE_ORCHESTRATOR_MODULE,
    STAGE30_9_3_GATE_STACK_REQUIRED,
    STAGE30_9_3_FAKE_PROOF_BASENAME,
    STAGE30_9_3_FAKE_PROOF_MODULE,
    STAGE30_9_3_INTEGRATION_RESULT_FIELDS,
    STAGE30_9_3_INTEGRATION_SCHEMA_VERSION,
    STAGE30_9_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_9_3_LIVE_GATE_DECISION_FIELDS,
    STAGE30_9_3_LIVE_GATE_INPUT_FIELDS,
    STAGE30_9_3_MINOR_VERSION,
    STAGE30_9_3_NEXT_ALLOWED_STEP,
    STAGE30_9_3_NEXT_ALLOWED_STEP_TITLE,
    STAGE30_9_3_PRIOR_STAGE,
    STAGE30_9_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_9_3_TEST_BASENAMES,
)
from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    STAGE30_9_3_INTEGRATION_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_9_3_MINOR_VERSION as MODELS_MINOR_VERSION,
    integration_result_field_names,
    live_gate_decision_field_names,
    live_gate_input_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Version + identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_9_3_MINOR_VERSION == "30.9.3"
    assert STAGE30_9_3_MINOR_VERSION == MODELS_MINOR_VERSION


def test_prior_stage_pinned() -> None:
    assert STAGE30_9_3_PRIOR_STAGE == "30.9.2"


def test_integration_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_9_3_INTEGRATION_SCHEMA_VERSION == (
        "stage30_9_3_v0_dip_filtered_live_gate"
    )
    assert STAGE30_9_3_INTEGRATION_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


def test_required_gate_stack_pinned() -> None:
    assert STAGE30_9_3_GATE_STACK_REQUIRED == (
        "30.10.1 offline tier-dip eligibility classifier",
        "30.10.2 optional pre-dispatch tier-dip gate",
        "30.10.3 gate artifact projection",
    )


def test_gate_decisions_pinned() -> None:
    assert STAGE30_9_3_GATE_DECISIONS == (
        "PASS_TO_DISPATCH",
        "SKIP_BEFORE_DISPATCH",
        "INVALID_INPUT",
    )
    assert STAGE30_9_3_DISPATCH_ALLOWED_GATE_DECISION == "PASS_TO_DISPATCH"


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_9_3_GATE_MODELS_BASENAME == (
        "stage30_9_3_dip_filtered_live_gate_models.py"
    )
    assert STAGE30_9_3_GATE_ADAPTER_BASENAME == (
        "stage30_9_3_dip_filtered_live_gate_adapter.py"
    )
    assert STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME == (
        "stage30_9_3_dip_filtered_live_gate_orchestrator.py"
    )
    assert STAGE30_9_3_FAKE_PROOF_BASENAME == (
        "stage30_9_3_fake_live_gate_integration_proof.py"
    )
    assert STAGE30_9_3_GATE_MODELS_MODULE == (
        "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models"
    )
    assert STAGE30_9_3_GATE_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter"
    )
    assert STAGE30_9_3_GATE_ORCHESTRATOR_MODULE == (
        "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_orchestrator"
    )
    assert STAGE30_9_3_FAKE_PROOF_MODULE == (
        "PHX2.stage30.stage30_9_3_fake_live_gate_integration_proof"
    )


def test_allowed_and_scanned_basenames_are_the_four_modules() -> None:
    expected = (
        STAGE30_9_3_GATE_MODELS_BASENAME,
        STAGE30_9_3_GATE_ADAPTER_BASENAME,
        STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME,
        STAGE30_9_3_FAKE_PROOF_BASENAME,
    )
    assert STAGE30_9_3_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_9_3_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_9_3_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.9.3 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_9_3_TEST_BASENAMES == (
        "test_stage_30_9_3_dip_filtered_live_gate_models.py",
        "test_stage_30_9_3_dip_filtered_live_gate_adapter.py",
        "test_stage_30_9_3_dip_filtered_live_gate_orchestrator.py",
        "test_stage_30_9_3_fake_live_gate_integration_proof.py",
        "test_stage_30_9_3_boundaries.py",
        "test_stage_30_9_3_manifest.py",
    )
    for basename in STAGE30_9_3_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.9.3 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_9_3_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    for forbidden in ("os", "json", "pathlib", "sqlite3", "zstandard", "time"):
        assert forbidden not in STAGE30_9_3_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_9_3_ALLOWED_PHX2_IMPORTS == (
        STAGE30_9_3_GATE_MODELS_MODULE,
        STAGE30_9_3_GATE_ADAPTER_MODULE,
        STAGE30_9_3_GATE_ORCHESTRATOR_MODULE,
        "PHX2.stage30.stage30_10_1_tier_dip_eligibility_models",
        "PHX2.stage30.stage30_10_2_pre_dispatch_gate",
        "PHX2.stage30.stage30_10_2_pre_dispatch_gate_models",
        "PHX2.stage30.stage30_10_3_gate_artifact_projector",
        "PHX2.stage30.stage30_10_3_gate_artifact_models",
    )
    for module in STAGE30_9_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    # The fake-proof module is a leaf entry point; it is NOT an import target.
    assert STAGE30_9_3_FAKE_PROOF_MODULE not in STAGE30_9_3_ALLOWED_PHX2_IMPORTS


# ---------------------------------------------------------------------------
# 4. Field-name tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_live_gate_input_fields_match_models() -> None:
    assert STAGE30_9_3_LIVE_GATE_INPUT_FIELDS == live_gate_input_field_names()


def test_live_gate_decision_fields_match_models() -> None:
    assert STAGE30_9_3_LIVE_GATE_DECISION_FIELDS == (
        live_gate_decision_field_names()
    )


def test_integration_result_fields_match_models() -> None:
    assert STAGE30_9_3_INTEGRATION_RESULT_FIELDS == (
        integration_result_field_names()
    )


def test_decision_fields_carry_transport_safety_negatives() -> None:
    for name in (
        "dispatch_failure_recorded",
        "transport_veto_used",
        "payload_refused_used",
        "dispatch_reservation_allowed",
        "suppressed_before_dispatch_reservation",
    ):
        assert name in STAGE30_9_3_LIVE_GATE_DECISION_FIELDS


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        STAGE30_9_3_LIVE_GATE_INPUT_FIELDS
        + STAGE30_9_3_LIVE_GATE_DECISION_FIELDS
        + STAGE30_9_3_INTEGRATION_RESULT_FIELDS
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
                f"Stage 30.9.3 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 5. Fake-proof expected counts + cross-check against the proof
# ---------------------------------------------------------------------------


def test_fake_proof_expected_counts_pinned() -> None:
    assert STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SEEN == 9
    assert STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_PASSED == 3
    assert STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SKIPPED == 5
    assert STAGE30_9_3_FAKE_PROOF_FULL_INVALID_INPUTS == 1
    assert STAGE30_9_3_FAKE_PROOF_FULL_DISPATCH_ATTEMPTS_RESERVED == 3
    assert STAGE30_9_3_FAKE_PROOF_FULL_WOULD_SEND_PRIVATE_DISCORD == 3
    assert STAGE30_9_3_FAKE_PROOF_DIP_PRESENT_DISPATCHES == 1
    assert STAGE30_9_3_FAKE_PROOF_NO_DIP_DISPATCHES == 0
    assert STAGE30_9_3_FAKE_PROOF_NO_DIP_CANDIDATES_SKIPPED == 5
    assert STAGE30_9_3_FAKE_PROOF_NO_DIP_INVALID_INPUTS == 1
    assert STAGE30_9_3_FAKE_PROOF_DISPATCH_FAILURES_RECORDED == 0
    assert STAGE30_9_3_FAKE_PROOF_TRANSPORT_VETO_COUNT == 0
    assert STAGE30_9_3_FAKE_PROOF_PAYLOAD_REFUSED_COUNT == 0


def test_fake_proof_expected_counts_match_the_proof() -> None:
    from PHX2.stage30.stage30_9_3_fake_live_gate_integration_proof import (
        run_stage30_9_3_dip_present_controlled_proof,
        run_stage30_9_3_full_gate_classification_proof,
        run_stage30_9_3_no_dip_controlled_proof,
    )

    _d, full, full_calls = run_stage30_9_3_full_gate_classification_proof()
    assert full.candidates_seen == STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SEEN
    assert full.candidates_passed_gate == (
        STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_PASSED
    )
    assert full.candidates_skipped_before_dispatch == (
        STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SKIPPED
    )
    assert full.invalid_inputs == STAGE30_9_3_FAKE_PROOF_FULL_INVALID_INPUTS
    assert full.dispatch_attempts_reserved == (
        STAGE30_9_3_FAKE_PROOF_FULL_DISPATCH_ATTEMPTS_RESERVED
    )
    assert full.would_send_private_discord_count == (
        STAGE30_9_3_FAKE_PROOF_FULL_WOULD_SEND_PRIVATE_DISCORD
    )
    assert full_calls == STAGE30_9_3_FAKE_PROOF_FULL_WOULD_SEND_PRIVATE_DISCORD
    assert full.dispatch_failures_recorded == (
        STAGE30_9_3_FAKE_PROOF_DISPATCH_FAILURES_RECORDED
    )
    assert full.transport_veto_count == STAGE30_9_3_FAKE_PROOF_TRANSPORT_VETO_COUNT
    assert full.payload_refused_count == (
        STAGE30_9_3_FAKE_PROOF_PAYLOAD_REFUSED_COUNT
    )

    _d2, dip, dip_calls = run_stage30_9_3_dip_present_controlled_proof()
    assert dip.would_send_private_discord_count == (
        STAGE30_9_3_FAKE_PROOF_DIP_PRESENT_DISPATCHES
    )
    assert dip_calls == STAGE30_9_3_FAKE_PROOF_DIP_PRESENT_DISPATCHES

    _d3, nodip, nodip_calls = run_stage30_9_3_no_dip_controlled_proof()
    assert nodip.would_send_private_discord_count == (
        STAGE30_9_3_FAKE_PROOF_NO_DIP_DISPATCHES
    )
    assert nodip_calls == STAGE30_9_3_FAKE_PROOF_NO_DIP_DISPATCHES
    assert nodip.candidates_skipped_before_dispatch == (
        STAGE30_9_3_FAKE_PROOF_NO_DIP_CANDIDATES_SKIPPED
    )
    assert nodip.invalid_inputs == STAGE30_9_3_FAKE_PROOF_NO_DIP_INVALID_INPUTS


# ---------------------------------------------------------------------------
# 6. Operator-auth gate + next allowed step
# ---------------------------------------------------------------------------


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_9_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


def test_next_allowed_step_is_controlled_operator_authorized_ceremony() -> None:
    assert STAGE30_9_3_NEXT_ALLOWED_STEP == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    lower = STAGE30_9_3_NEXT_ALLOWED_STEP_TITLE.lower()
    assert "operator-authorized" in lower
    assert "live ceremony" in lower
    assert "automatic live execution" in lower


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_9_3_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_9_3_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_9_3_FORBIDDEN_SURFACES)
    for token in (
        "live run",
        "live provider call",
        "real Discord send",
        "env read",
        "real transport dispatch reservation",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "dispatch sink call without PASS_TO_DISPATCH",
        "Stage 28 suppression-logic edit",
        "Stage 30.3 compact orchestrator edit",
        "Stage 30.4 compact orchestrator edit",
        "existing live runner edit",
        "new provider",
        "new readiness gate",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "default storage root",
        "public routing",
        "subscriber routing",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "commit",
        "tag",
        "push",
        "Stage 30.9.4+ implementation file",
        "Stage 30.10.4+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.9.3 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the Stage 30.9.3 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_9_3_surface() -> None:
    for name in (
        "STAGE30_9_3_MINOR_VERSION",
        "STAGE30_9_3_PRIOR_STAGE",
        "STAGE30_9_3_INTEGRATION_SCHEMA_VERSION",
        "STAGE30_9_3_GATE_STACK_REQUIRED",
        "STAGE30_9_3_GATE_DECISIONS",
        "STAGE30_9_3_DISPATCH_ALLOWED_GATE_DECISION",
        "STAGE30_9_3_GATE_MODELS_BASENAME",
        "STAGE30_9_3_GATE_ADAPTER_BASENAME",
        "STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME",
        "STAGE30_9_3_FAKE_PROOF_BASENAME",
        "STAGE30_9_3_GATE_MODELS_MODULE",
        "STAGE30_9_3_GATE_ADAPTER_MODULE",
        "STAGE30_9_3_GATE_ORCHESTRATOR_MODULE",
        "STAGE30_9_3_FAKE_PROOF_MODULE",
        "STAGE30_9_3_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_9_3_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_9_3_TEST_BASENAMES",
        "STAGE30_9_3_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_9_3_ALLOWED_PHX2_IMPORTS",
        "STAGE30_9_3_LIVE_GATE_INPUT_FIELDS",
        "STAGE30_9_3_LIVE_GATE_DECISION_FIELDS",
        "STAGE30_9_3_INTEGRATION_RESULT_FIELDS",
        "STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SEEN",
        "STAGE30_9_3_FAKE_PROOF_DIP_PRESENT_DISPATCHES",
        "STAGE30_9_3_FAKE_PROOF_NO_DIP_DISPATCHES",
        "STAGE30_9_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_9_3_INTEGRATION_NOTE",
        "STAGE30_9_3_NEXT_ALLOWED_STEP",
        "STAGE30_9_3_NEXT_ALLOWED_STEP_TITLE",
        "STAGE30_9_3_FORBIDDEN_SURFACES",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_9_constants_still_present() -> None:
    # The Stage 30.9.3 manifest edit is purely additive: the Stage 30.9.0 /
    # 30.9.1 / 30.9.2 constants survive.
    for name in (
        "STAGE30_9_STAGE_ID",
        "STAGE30_9_PLANNED_SUBSTAGES",
        "STAGE30_9_NEXT_ALLOWED_STAGE",
        "STAGE30_9_2_RESUME_ID",
        "STAGE30_9_2_FORBIDDEN_SURFACES",
        "STAGE30_9_1_MINOR_VERSION",
    ):
        assert name in M.__all__


def test_planned_substages_unchanged() -> None:
    # The Stage 30.9.3 seam is an additively admitted slice; the original
    # planned-substage tuple is unchanged (it stops at 30.9.2).
    assert M.STAGE30_9_PLANNED_SUBSTAGES == ("30.9.0", "30.9.1", "30.9.2")
    assert M.STAGE30_9_NEXT_ALLOWED_STAGE == "30.9.1"


# ---------------------------------------------------------------------------
# 9. Stage 30.9.4+ future guard
# ---------------------------------------------------------------------------


def test_inventory_admits_no_stage_30_9_4_plus_file() -> None:
    import re

    pattern = re.compile(r"stage_?30_9_(\d+)")
    inventory = (
        tuple(STAGE30_9_3_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_9_3_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in pattern.finditer(basename.lower()):
            if int(match.group(1)) >= 4:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.9.3 inventory must not admit a Stage 30.9.4+ file yet; "
        f"saw {violations!r}"
    )
