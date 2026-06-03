"""Stage 30.11.5 manifest pin tests.

Pins the Stage 30.11.5 manifest constants (minor version, live wiring schema
version, the five production basenames + module paths, the committed composed
sibling module paths, the inventory + scanned basenames, the test basenames, the
stdlib + PHX2 import allowlists, the assembly decision / reason + transport
status tokens, the projection + model field names, the hard caps + defaults, the
expected proof counts, the operator-authorized next-step token, the slice
forbidden surfaces, the operator-auth live-ceremony note), asserts the production
+ test files exist, cross-checks the mirrored schema version + tokens + field
names against the Stage 30.11.5 models module, cross-checks the expected counts
against the fake proof, confirms the Stage 30.11.0..30.11.4 constants + planned
substages + family next-allowed pointer survive unchanged, and pins the Stage
30.11.6+ / Stage 31 future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_3_NEXT_ALLOWED_STAGE,
    STAGE30_11_4_NEXT_ALLOWED_STAGE,
    STAGE30_11_5_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_5_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_5_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_5_ASSEMBLY_DECISIONS,
    STAGE30_11_5_ASSEMBLY_PASS_DECISION,
    STAGE30_11_5_ASSEMBLY_PASS_REASON,
    STAGE30_11_5_ASSEMBLY_REASONS,
    STAGE30_11_5_ASSEMBLY_RESULT_FIELDS,
    STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME,
    STAGE30_11_5_BOUNDED_LIVE_RUNNER_MODULE,
    STAGE30_11_5_BOUNDED_RUN_RESULT_FIELDS,
    STAGE30_11_5_BOUNDED_RUN_SUMMARY_FIELDS,
    STAGE30_11_5_DEFAULT_MAX_CANDIDATES,
    STAGE30_11_5_DEFAULT_MAX_DISPATCHES,
    STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS,
    STAGE30_11_5_EXPECTED_ASSEMBLED,
    STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED,
    STAGE30_11_5_EXPECTED_BRIDGED,
    STAGE30_11_5_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED,
    STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED,
    STAGE30_11_5_EXPECTED_GATE_PASSED,
    STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN,
    STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE,
    STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE,
    STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS,
    STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_BASENAME,
    STAGE30_11_5_FORBIDDEN_SURFACES,
    STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_BASENAME,
    STAGE30_11_5_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME,
    STAGE30_11_5_LIVE_WIRING_MODELS_MODULE,
    STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION,
    STAGE30_11_5_MAX_CANDIDATES_HARD_CAP,
    STAGE30_11_5_MAX_DISPATCHES_HARD_CAP,
    STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP,
    STAGE30_11_5_MINOR_VERSION,
    STAGE30_11_5_NEXT_ALLOWED_STAGE,
    STAGE30_11_5_PRIVATE_OPERATOR_PAYLOAD_FIELDS,
    STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_BASENAME,
    STAGE30_11_5_PROJECTION_FIELDS,
    STAGE30_11_5_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_5_STAGE30_11_1_BRIDGE_MODELS_MODULE,
    STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
    STAGE30_11_5_TEST_BASENAMES,
    STAGE30_11_5_TRANSPORT_ACCEPT_STATUS,
    STAGE30_11_5_TRANSPORT_CLIENT_RESULT_FIELDS,
    STAGE30_11_5_TRANSPORT_STATUSES,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_PLANNED_SUBSTAGES,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    STAGE30_11_5_ASSEMBLY_DECISIONS as MODELS_ASSEMBLY_DECISIONS,
    STAGE30_11_5_ASSEMBLY_REASONS as MODELS_ASSEMBLY_REASONS,
    STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_5_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_11_5_PROJECTION_FIELDS as MODELS_PROJECTION_FIELDS,
    STAGE30_11_5_TRANSPORT_STATUSES as MODELS_TRANSPORT_STATUSES,
    bounded_run_result_field_names,
    bounded_run_summary_field_names,
    live_candidate_assembly_result_field_names,
    private_operator_payload_field_names,
    transport_client_result_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor + schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_5_MINOR_VERSION == "30.11.5"
    assert STAGE30_11_5_MINOR_VERSION == MODELS_MINOR_VERSION


def test_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION == (
        "stage30_11_5_v0_live_wiring"
    )
    assert STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_allowed_and_scanned_basenames_are_the_five_modules() -> None:
    expected = (
        STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME,
        STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_BASENAME,
        STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_BASENAME,
        STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME,
        STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_BASENAME,
    )
    assert STAGE30_11_5_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_5_SCANNED_PRODUCTION_BASENAMES == expected


def test_basenames_pinned() -> None:
    assert STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME == (
        "stage30_11_5_live_wiring_models.py"
    )
    assert STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_BASENAME == (
        "stage30_11_5_live_candidate_snapshot_assembler.py"
    )
    assert STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_BASENAME == (
        "stage30_11_5_private_transport_adapter.py"
    )
    assert STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME == (
        "stage30_11_5_bounded_live_runner.py"
    )
    assert STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_BASENAME == (
        "stage30_11_5_fake_live_wiring_proof.py"
    )


def test_composed_sibling_modules_pinned() -> None:
    assert STAGE30_11_5_STAGE30_11_1_BRIDGE_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_1_live_candidate_bridge_models"
    )
    assert STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE == (
        "PHX2.stage30.stage30_11_2_runtime_gate_seam"
    )
    assert STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_3_private_sink_adapter"
    )
    assert STAGE30_11_5_BOUNDED_LIVE_RUNNER_MODULE == (
        "PHX2.stage30.stage30_11_5_bounded_live_runner"
    )


def test_production_files_exist() -> None:
    for basename in STAGE30_11_5_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.5 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_5_TEST_BASENAMES == (
        "test_stage_30_11_5_live_wiring_models.py",
        "test_stage_30_11_5_live_candidate_snapshot_assembler.py",
        "test_stage_30_11_5_private_transport_adapter.py",
        "test_stage_30_11_5_bounded_live_runner.py",
        "test_stage_30_11_5_fake_live_wiring_proof.py",
        "test_stage_30_11_5_boundaries.py",
        "test_stage_30_11_5_manifest.py",
    )
    for basename in STAGE30_11_5_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.5 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_5_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    for forbidden in ("os", "json", "pathlib", "sqlite3", "time", "datetime"):
        assert forbidden not in STAGE30_11_5_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_11_5_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_5_LIVE_WIRING_MODELS_MODULE,
        M.STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_MODULE,
        M.STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_MODULE,
        STAGE30_11_5_BOUNDED_LIVE_RUNNER_MODULE,
        STAGE30_11_5_STAGE30_11_1_BRIDGE_MODELS_MODULE,
        M.STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
        STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
        M.STAGE30_11_5_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
        M.STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
        STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
    )
    assert len(STAGE30_11_5_ALLOWED_PHX2_IMPORTS) == 10
    for module in STAGE30_11_5_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_5_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Tokens (mirrored from models)
# ---------------------------------------------------------------------------


def test_assembly_tokens_pinned_and_match_models() -> None:
    assert STAGE30_11_5_ASSEMBLY_DECISIONS == (
        "ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT",
        "REJECTED_MISSING_REQUIRED_FIELD",
        "REJECTED_INVALID_FIELD_SHAPE",
    )
    assert STAGE30_11_5_ASSEMBLY_PASS_DECISION == (
        "ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT"
    )
    assert STAGE30_11_5_ASSEMBLY_REASONS == (
        "READY_FOR_BRIDGE",
        "MISSING_REQUIRED_CANDIDATE_FIELD",
        "INVALID_CANDIDATE_FIELD_SHAPE",
    )
    assert STAGE30_11_5_ASSEMBLY_PASS_REASON == "READY_FOR_BRIDGE"
    assert STAGE30_11_5_ASSEMBLY_DECISIONS == MODELS_ASSEMBLY_DECISIONS
    assert STAGE30_11_5_ASSEMBLY_REASONS == MODELS_ASSEMBLY_REASONS


def test_transport_statuses_pinned_and_match_models() -> None:
    assert STAGE30_11_5_TRANSPORT_STATUSES == (
        "WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE",
        "TRANSPORT_REJECTED",
    )
    assert STAGE30_11_5_TRANSPORT_ACCEPT_STATUS == (
        "WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE"
    )
    assert STAGE30_11_5_TRANSPORT_STATUSES == MODELS_TRANSPORT_STATUSES


# ---------------------------------------------------------------------------
# 5. Field tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_projection_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_5_PROJECTION_FIELDS == MODELS_PROJECTION_FIELDS
    assert "current_market_cap_usd" in STAGE30_11_5_PROJECTION_FIELDS
    assert "tier_hint" in STAGE30_11_5_PROJECTION_FIELDS


def test_model_field_tuples_pinned_and_match_models() -> None:
    assert STAGE30_11_5_ASSEMBLY_RESULT_FIELDS == (
        live_candidate_assembly_result_field_names()
    )
    assert STAGE30_11_5_PRIVATE_OPERATOR_PAYLOAD_FIELDS == (
        private_operator_payload_field_names()
    )
    assert STAGE30_11_5_TRANSPORT_CLIENT_RESULT_FIELDS == (
        transport_client_result_field_names()
    )
    assert STAGE30_11_5_BOUNDED_RUN_SUMMARY_FIELDS == (
        bounded_run_summary_field_names()
    )
    assert STAGE30_11_5_BOUNDED_RUN_RESULT_FIELDS == (
        bounded_run_result_field_names()
    )


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        STAGE30_11_5_ASSEMBLY_RESULT_FIELDS
        + STAGE30_11_5_PRIVATE_OPERATOR_PAYLOAD_FIELDS
        + STAGE30_11_5_TRANSPORT_CLIENT_RESULT_FIELDS
        + STAGE30_11_5_BOUNDED_RUN_SUMMARY_FIELDS
        + STAGE30_11_5_BOUNDED_RUN_RESULT_FIELDS
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
                f"Stage 30.11.5 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. Hard caps + defaults
# ---------------------------------------------------------------------------


def test_hard_caps_and_defaults_pinned() -> None:
    assert STAGE30_11_5_MAX_DISPATCHES_HARD_CAP == 1
    assert STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP == 60
    assert STAGE30_11_5_MAX_CANDIDATES_HARD_CAP == 10
    assert STAGE30_11_5_DEFAULT_MAX_DISPATCHES == 1
    assert STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS == 60
    assert STAGE30_11_5_DEFAULT_MAX_CANDIDATES == 10


# ---------------------------------------------------------------------------
# 7. Expected proof counts (mirrored + cross-checked vs the fake proof)
# ---------------------------------------------------------------------------


def test_expected_counts_pinned() -> None:
    assert STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN == 4
    assert STAGE30_11_5_EXPECTED_ASSEMBLED == 3
    assert STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED == 1
    assert STAGE30_11_5_EXPECTED_CANDIDATES_SEEN == 3
    assert STAGE30_11_5_EXPECTED_BRIDGED == 2
    assert STAGE30_11_5_EXPECTED_GATE_PASSED == 1
    assert STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED == 1
    assert STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED == 1
    assert STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE == 1
    assert STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE == 1
    assert STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID == "cand-tier1"
    assert STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT == "mint-tier1"


def test_expected_counts_match_the_fake_proof() -> None:
    from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
        run_stage30_11_5_fake_live_wiring_proof,
    )

    result, client = run_stage30_11_5_fake_live_wiring_proof()
    s = result.summary
    assert s.source_items_seen == STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN
    assert s.assembled == STAGE30_11_5_EXPECTED_ASSEMBLED
    assert s.assembly_rejected == STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED
    assert s.candidates_seen == STAGE30_11_5_EXPECTED_CANDIDATES_SEEN
    assert s.bridged == STAGE30_11_5_EXPECTED_BRIDGED
    assert s.gate_passed == STAGE30_11_5_EXPECTED_GATE_PASSED
    assert s.dispatch_attempted == STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED
    assert s.dispatch_accepted == STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED
    assert s.suppressed_by_bridge == STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE
    assert s.suppressed_by_gate == STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE
    assert client.attempted == STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS
    assert client.accepted == STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS
    assert client.candidate_ids == [STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID]
    assert client.token_mints == [STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT]


# ---------------------------------------------------------------------------
# 8. Next allowed step + family pointer + earlier scoped pointers unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_step_is_the_operator_authorized_ceremony() -> None:
    assert STAGE30_11_5_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert "30.11.6" not in STAGE30_11_5_NEXT_ALLOWED_STAGE
    # The earlier scoped pointers + the family pointer survive unchanged.
    assert STAGE30_11_4_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert STAGE30_11_3_NEXT_ALLOWED_STAGE == "30.11.4"
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


def test_planned_substages_unchanged() -> None:
    # The Stage 30.11.5 manifest edit is additive: the family planned-substage
    # tuple still stops at 30.11.4 (it described the original plan); the 30.11.5
    # slice is admitted via its own scoped constants.
    assert STAGE30_11_PLANNED_SUBSTAGES == (
        "30.11.0",
        "30.11.1",
        "30.11.2",
        "30.11.3",
        "30.11.4",
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_5_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 9. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_5_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_5_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_5_FORBIDDEN_SURFACES)
    for token in (
        "controlled live ceremony executed in this stage",
        "real candidate source",
        "real transport call",
        "real Discord send",
        "Discord send",
        "real dispatch reservation",
        "live run",
        "live provider call",
        "env read",
        "wall-clock read",
        "new live runner",
        "new provider",
        "new dip gate",
        "max_dispatches above 1",
        "max_runtime_seconds above 60",
        "max_candidates above 10",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "daemon",
        "background service",
        "autorestart loop",
        "unbounded loop",
        "Stage 27 / 28 / 29 candidate-record import",
        "Stage 28 suppression-logic edit",
        "Stage 29 live provider / session edit",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "public routing",
        "subscriber routing",
        "paid tiers",
        "Telegram",
        "wallet / signing",
        "enforcement activation",
        "commit",
        "tag",
        "push",
        "Stage 30.11.6+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.5 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 10. Manifest __all__ exports the Stage 30.11.5 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_5_surface() -> None:
    for name in (
        "STAGE30_11_5_MINOR_VERSION",
        "STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION",
        "STAGE30_11_5_SOURCE_STAGE",
        "STAGE30_11_5_LIVE_WIRING_MODELS_MODULE",
        "STAGE30_11_5_BOUNDED_LIVE_RUNNER_MODULE",
        "STAGE30_11_5_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_5_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_5_TEST_BASENAMES",
        "STAGE30_11_5_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_5_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_5_ASSEMBLY_DECISIONS",
        "STAGE30_11_5_ASSEMBLY_REASONS",
        "STAGE30_11_5_TRANSPORT_STATUSES",
        "STAGE30_11_5_PROJECTION_FIELDS",
        "STAGE30_11_5_ASSEMBLY_RESULT_FIELDS",
        "STAGE30_11_5_BOUNDED_RUN_SUMMARY_FIELDS",
        "STAGE30_11_5_MAX_DISPATCHES_HARD_CAP",
        "STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID",
        "STAGE30_11_5_NEXT_ALLOWED_STAGE",
        "STAGE30_11_5_FORBIDDEN_SURFACES",
        "STAGE30_11_5_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_5_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_through_30_11_4_constants_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_1_MINOR_VERSION",
        "STAGE30_11_2_MINOR_VERSION",
        "STAGE30_11_3_MINOR_VERSION",
        "STAGE30_11_4_MINOR_VERSION",
        "STAGE30_11_4_NEXT_ALLOWED_STAGE",
        "STAGE30_11_4_ALLOWED_STAGE30_BASENAMES",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 11. Stage 30.11.6+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_6_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_5_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_5_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 6:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.5 inventory must not admit a Stage 30.11.6+ file yet; "
        f"saw {violations!r}"
    )
