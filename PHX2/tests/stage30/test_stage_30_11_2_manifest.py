"""Stage 30.11.2 manifest pin tests.

Pins the Stage 30.11.2 manifest constants (minor version, runtime gate schema
version, the three production basenames + module paths, the committed composed
sibling module paths, the inventory + scanned basenames, the test basenames, the
stdlib + PHX2 import allowlists, the runtime decision / reason tokens + sentinel,
the config / outcome / summary / fake-result field names, the fake proof expected
counts, the slice-scoped next-allowed Stage 30.11.3 token, the slice forbidden
surfaces, the operator-auth live-ceremony note), asserts the production + test
files exist, cross-checks the mirrored schema version + decision / reason tokens
+ field names against the Stage 30.11.2 models module, cross-checks the fake proof
expected counts against the proof, confirms the Stage 30.11.0 / 30.11.1 constants
+ planned substages + family next-allowed pointer survive unchanged, and pins the
Stage 30.11.3+ future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_1_NEXT_ALLOWED_STAGE,
    STAGE30_11_2_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_2_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_2_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_2_FAKE_DISPATCH_RESULT_FIELDS,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ACCEPTED,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTED,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_BRIDGE,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_GATE,
    STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_BASENAME,
    STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
    STAGE30_11_2_FORBIDDEN_SURFACES,
    STAGE30_11_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_2_MINOR_VERSION,
    STAGE30_11_2_NEXT_ALLOWED_STAGE,
    STAGE30_11_2_NOT_EVALUATED,
    STAGE30_11_2_RUNTIME_DECISIONS,
    STAGE30_11_2_RUNTIME_DISPATCH_DECISION,
    STAGE30_11_2_RUNTIME_DISPATCH_REASON,
    STAGE30_11_2_RUNTIME_GATE_CONFIG_FIELDS,
    STAGE30_11_2_RUNTIME_GATE_MODELS_BASENAME,
    STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
    STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION,
    STAGE30_11_2_RUNTIME_GATE_SEAM_BASENAME,
    STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_2_RUNTIME_OUTCOME_FIELDS,
    STAGE30_11_2_RUNTIME_REASONS,
    STAGE30_11_2_RUNTIME_SUMMARY_FIELDS,
    STAGE30_11_2_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_2_STAGE30_9_3_GATE_ADAPTER_MODULE,
    STAGE30_11_2_STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_11_2_STAGE30_10_2_GATE_MODELS_MODULE,
    STAGE30_11_2_STAGE30_11_1_BRIDGE_MODELS_MODULE,
    STAGE30_11_2_STAGE30_11_1_BRIDGE_MODULE,
    STAGE30_11_2_TEST_BASENAMES,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_PLANNED_SUBSTAGES,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    STAGE30_11_2_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_11_2_NOT_EVALUATED as MODELS_NOT_EVALUATED,
    STAGE30_11_2_RUNTIME_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_2_RUNTIME_REASONS as MODELS_REASONS,
    fake_dispatch_result_field_names,
    runtime_gate_candidate_outcome_field_names,
    runtime_gate_config_field_names,
    runtime_gate_summary_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_2_MINOR_VERSION == "30.11.2"
    assert STAGE30_11_2_MINOR_VERSION == MODELS_MINOR_VERSION


def test_runtime_gate_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION == (
        "stage30_11_2_v0_runtime_gate_seam"
    )
    assert STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_2_RUNTIME_GATE_MODELS_BASENAME == (
        "stage30_11_2_runtime_gate_models.py"
    )
    assert STAGE30_11_2_RUNTIME_GATE_SEAM_BASENAME == (
        "stage30_11_2_runtime_gate_seam.py"
    )
    assert STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_BASENAME == (
        "stage30_11_2_fake_runtime_gate_proof.py"
    )
    assert STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_2_runtime_gate_models"
    )
    assert STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE == (
        "PHX2.stage30.stage30_11_2_runtime_gate_seam"
    )
    assert STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_2_fake_runtime_gate_proof"
    )


def test_composed_sibling_modules_pinned() -> None:
    assert STAGE30_11_2_STAGE30_11_1_BRIDGE_MODULE == (
        "PHX2.stage30.stage30_11_1_live_candidate_bridge"
    )
    assert STAGE30_11_2_STAGE30_11_1_BRIDGE_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_1_live_candidate_bridge_models"
    )
    assert STAGE30_11_2_STAGE30_9_3_GATE_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter"
    )
    assert STAGE30_11_2_STAGE30_9_3_GATE_MODELS_MODULE == (
        "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models"
    )
    assert STAGE30_11_2_STAGE30_10_2_GATE_MODELS_MODULE == (
        "PHX2.stage30.stage30_10_2_pre_dispatch_gate_models"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_2_RUNTIME_GATE_MODELS_BASENAME,
        STAGE30_11_2_RUNTIME_GATE_SEAM_BASENAME,
        STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_BASENAME,
    )
    assert STAGE30_11_2_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_2_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_2_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.2 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_2_TEST_BASENAMES == (
        "test_stage_30_11_2_runtime_gate_models.py",
        "test_stage_30_11_2_runtime_gate_seam.py",
        "test_stage_30_11_2_fake_runtime_gate_proof.py",
        "test_stage_30_11_2_boundaries.py",
        "test_stage_30_11_2_manifest.py",
    )
    for basename in STAGE30_11_2_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.2 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_2_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    for forbidden in (
        "os",
        "json",
        "pathlib",
        "sqlite3",
        "zstandard",
        "time",
        "datetime",
    ):
        assert forbidden not in STAGE30_11_2_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_11_2_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
        STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
        STAGE30_11_2_STAGE30_11_1_BRIDGE_MODULE,
        STAGE30_11_2_STAGE30_11_1_BRIDGE_MODELS_MODULE,
        STAGE30_11_2_STAGE30_9_3_GATE_ADAPTER_MODULE,
        STAGE30_11_2_STAGE30_9_3_GATE_MODELS_MODULE,
        STAGE30_11_2_STAGE30_10_2_GATE_MODELS_MODULE,
    )
    for module in STAGE30_11_2_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_2_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "transport", "suppress", "renderer"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Runtime decisions + reasons + sentinel (mirrored from models)
# ---------------------------------------------------------------------------


def test_runtime_decisions_pinned_and_match_models() -> None:
    assert STAGE30_11_2_RUNTIME_DECISIONS == (
        "DISPATCHED_AFTER_DIP_GATE_PASS",
        "SUPPRESSED_BY_BRIDGE",
        "SUPPRESSED_BY_DIP_GATE",
        "STOPPED_BY_CANDIDATE_CAP",
        "STOPPED_BY_DISPATCH_CAP",
        "STOPPED_BY_RUNTIME_SECONDS",
        "INVALID_RUNTIME_INPUT",
    )
    assert STAGE30_11_2_RUNTIME_DISPATCH_DECISION == (
        "DISPATCHED_AFTER_DIP_GATE_PASS"
    )
    assert STAGE30_11_2_RUNTIME_DECISIONS == MODELS_DECISIONS


def test_runtime_reasons_pinned_and_match_models() -> None:
    assert STAGE30_11_2_RUNTIME_REASONS == (
        "PASS_TO_FAKE_DISPATCH",
        "BRIDGE_SKIPPED_OR_INVALID",
        "DIP_GATE_SKIPPED",
        "CANDIDATE_CAP_REACHED",
        "DISPATCH_CAP_REACHED",
        "RUNTIME_SECONDS_REACHED",
        "INVALID_CONFIG_OR_INPUT",
    )
    assert STAGE30_11_2_RUNTIME_DISPATCH_REASON == "PASS_TO_FAKE_DISPATCH"
    assert STAGE30_11_2_RUNTIME_REASONS == MODELS_REASONS


def test_not_evaluated_sentinel_pinned_and_matches_models() -> None:
    assert STAGE30_11_2_NOT_EVALUATED == "NOT_EVALUATED"
    assert STAGE30_11_2_NOT_EVALUATED == MODELS_NOT_EVALUATED
    assert STAGE30_11_2_NOT_EVALUATED not in STAGE30_11_2_RUNTIME_DECISIONS
    assert STAGE30_11_2_NOT_EVALUATED not in STAGE30_11_2_RUNTIME_REASONS


# ---------------------------------------------------------------------------
# 5. Field-name tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_config_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_2_RUNTIME_GATE_CONFIG_FIELDS == (
        "max_runtime_seconds",
        "max_candidates",
        "max_dispatches",
        "created_at_utc",
    )
    assert STAGE30_11_2_RUNTIME_GATE_CONFIG_FIELDS == (
        runtime_gate_config_field_names()
    )


def test_outcome_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_2_RUNTIME_OUTCOME_FIELDS == (
        "candidate_id",
        "token_mint",
        "bridge_decision",
        "gate_decision",
        "runtime_decision",
        "runtime_reason",
        "dispatch_attempted",
        "dispatch_accepted",
        "created_at_utc",
    )
    assert STAGE30_11_2_RUNTIME_OUTCOME_FIELDS == (
        runtime_gate_candidate_outcome_field_names()
    )


def test_summary_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_2_RUNTIME_SUMMARY_FIELDS == (
        "candidates_seen",
        "bridged",
        "gate_passed",
        "dispatch_attempted",
        "dispatch_accepted",
        "suppressed_by_bridge",
        "suppressed_by_gate",
        "stopped_by_candidate_cap",
        "stopped_by_dispatch_cap",
        "stopped_by_runtime_seconds",
        "invalid_inputs",
        "created_at_utc",
    )
    assert STAGE30_11_2_RUNTIME_SUMMARY_FIELDS == (
        runtime_gate_summary_field_names()
    )


def test_fake_dispatch_result_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_2_FAKE_DISPATCH_RESULT_FIELDS == (
        "accepted",
        "candidate_id",
        "token_mint",
        "created_at_utc",
    )
    assert STAGE30_11_2_FAKE_DISPATCH_RESULT_FIELDS == (
        fake_dispatch_result_field_names()
    )


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        STAGE30_11_2_RUNTIME_GATE_CONFIG_FIELDS
        + STAGE30_11_2_RUNTIME_OUTCOME_FIELDS
        + STAGE30_11_2_RUNTIME_SUMMARY_FIELDS
        + STAGE30_11_2_FAKE_DISPATCH_RESULT_FIELDS
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
                f"Stage 30.11.2 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. Fake proof expected counts
# ---------------------------------------------------------------------------


def test_fake_proof_expected_counts_pinned() -> None:
    assert STAGE30_11_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN == 5
    assert STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED == 2
    assert STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED == 1
    assert STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTED == 1
    assert STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ACCEPTED == 1
    assert STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_BRIDGE == 3
    assert STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_GATE == 1
    assert STAGE30_11_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS == 1
    # The bridged / suppressed partition holds, and the gate split holds.
    assert (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED
        + STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_BRIDGE
        == STAGE30_11_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN
    )
    assert (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED
        + STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_GATE
        == STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED
    )
    # Only the dip dispatches; the attempt is accepted.
    assert (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTED
        == STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED
    )


def test_fake_proof_expected_counts_match_the_proof() -> None:
    from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
        run_stage30_11_2_fake_runtime_gate_proof,
    )

    _outcomes, summary, _sink = run_stage30_11_2_fake_runtime_gate_proof()
    assert summary.candidates_seen == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN
    )
    assert summary.bridged == STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED
    assert summary.gate_passed == STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED
    assert summary.dispatch_attempted == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTED
    )
    assert summary.dispatch_accepted == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ACCEPTED
    )
    assert summary.suppressed_by_bridge == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_BRIDGE
    )
    assert summary.suppressed_by_gate == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_GATE
    )
    assert summary.invalid_inputs == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS
    )


# ---------------------------------------------------------------------------
# 7. Next allowed stage + family pointer + planned substages unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_stage_is_30_11_3_and_family_pointers_intact() -> None:
    # The 30.11.2-scoped pointer advances to 30.11.3; the Stage 30.11.0 family
    # pointer stays pinned at 30.11.1 and the 30.11.1-scoped pointer stays at
    # 30.11.2 (mirrors the Stage 30.9 / 30.10 manifest convention).
    assert STAGE30_11_2_NEXT_ALLOWED_STAGE == "30.11.3"
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
    joined = " ".join(STAGE30_11_PLANNED_SUBSTAGES)
    assert "30.12" not in joined
    assert "31" not in joined


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 8. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_2_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_2_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_2_FORBIDDEN_SURFACES)
    for token in (
        "real dispatch sink",
        "dispatch reservation",
        "real Discord send",
        "Discord send",
        "live run",
        "live provider call",
        "env read",
        "wall-clock read",
        "new live runner",
        "new provider",
        "new readiness gate",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "daemon",
        "background service",
        "autorestart loop",
        "unbounded loop",
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
        "Stage 30.11.3+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.2 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 9. Manifest __all__ exports the Stage 30.11.2 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_2_surface() -> None:
    for name in (
        "STAGE30_11_2_MINOR_VERSION",
        "STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION",
        "STAGE30_11_2_RUNTIME_GATE_MODELS_BASENAME",
        "STAGE30_11_2_RUNTIME_GATE_SEAM_BASENAME",
        "STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_BASENAME",
        "STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE",
        "STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE",
        "STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE",
        "STAGE30_11_2_STAGE30_11_1_BRIDGE_MODULE",
        "STAGE30_11_2_STAGE30_11_1_BRIDGE_MODELS_MODULE",
        "STAGE30_11_2_STAGE30_9_3_GATE_ADAPTER_MODULE",
        "STAGE30_11_2_STAGE30_9_3_GATE_MODELS_MODULE",
        "STAGE30_11_2_STAGE30_10_2_GATE_MODELS_MODULE",
        "STAGE30_11_2_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_2_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_2_TEST_BASENAMES",
        "STAGE30_11_2_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_2_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_2_RUNTIME_DECISIONS",
        "STAGE30_11_2_RUNTIME_DISPATCH_DECISION",
        "STAGE30_11_2_RUNTIME_REASONS",
        "STAGE30_11_2_RUNTIME_DISPATCH_REASON",
        "STAGE30_11_2_NOT_EVALUATED",
        "STAGE30_11_2_RUNTIME_GATE_CONFIG_FIELDS",
        "STAGE30_11_2_RUNTIME_OUTCOME_FIELDS",
        "STAGE30_11_2_RUNTIME_SUMMARY_FIELDS",
        "STAGE30_11_2_FAKE_DISPATCH_RESULT_FIELDS",
        "STAGE30_11_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN",
        "STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED",
        "STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED",
        "STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTED",
        "STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ACCEPTED",
        "STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_BRIDGE",
        "STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_GATE",
        "STAGE30_11_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS",
        "STAGE30_11_2_NEXT_ALLOWED_STAGE",
        "STAGE30_11_2_NEXT_ALLOWED_STAGE_TITLE",
        "STAGE30_11_2_FORBIDDEN_SURFACES",
        "STAGE30_11_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_2_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_and_30_11_1_constants_still_present() -> None:
    # The Stage 30.11.2 manifest edit is purely additive: the Stage 30.11.0 /
    # 30.11.1 constants survive.
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
        "STAGE30_11_1_MINOR_VERSION",
        "STAGE30_11_1_BRIDGE_SCHEMA_VERSION",
        "STAGE30_11_1_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_1_TEST_BASENAMES",
        "STAGE30_11_1_NEXT_ALLOWED_STAGE",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 10. Stage 30.11.3+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_3_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_2_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_2_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 3:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.2 inventory must not admit a Stage 30.11.3+ file yet; "
        f"saw {violations!r}"
    )
