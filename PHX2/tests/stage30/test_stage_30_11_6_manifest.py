"""Stage 30.11.6 manifest pin tests.

Pins the Stage 30.11.6 manifest constants (minor version, candidate-source schema
version, the four production basenames + module paths, the committed composed
sibling module path, the inventory + scanned basenames, the test basenames, the
stdlib + PHX2 import allowlists, the projection / harvest decision + reason tokens
+ the not-projected sentinel, the projection + model field names, the hard cap +
default + candidate-id prefix, the expected proof counts, the operator-authorized
next-step token, the slice forbidden surfaces, the operator-auth live-ceremony
note), asserts the production + test files exist, cross-checks the mirrored schema
version + tokens + field names against the Stage 30.11.6 models module, cross-checks
the expected counts against the fake proof, confirms the Stage 30.11.0..30.11.5
constants + planned substages + family next-allowed pointer survive unchanged, and
pins the Stage 30.11.7+ / Stage 31 future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_5_NEXT_ALLOWED_STAGE,
    STAGE30_11_6_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_6_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_6_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME,
    STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_MODULE,
    STAGE30_11_6_CANDIDATE_PROJECTION_FIELDS,
    STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME,
    STAGE30_11_6_CANDIDATE_SOURCE_MODELS_MODULE,
    STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION,
    STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX,
    STAGE30_11_6_DEFAULT_MAX_HARVEST,
    STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_6_EXPECTED_EVENTS_SEEN,
    STAGE30_11_6_EXPECTED_HARVESTED,
    STAGE30_11_6_EXPECTED_RUNNER_BRIDGED,
    STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN,
    STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ACCEPTED,
    STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ATTEMPTED,
    STAGE30_11_6_EXPECTED_RUNNER_GATE_PASSED,
    STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED,
    STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED,
    STAGE30_11_6_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_6_EXPECTED_TRANSPORT_ATTEMPTS,
    STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_BASENAME,
    STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_MODULE,
    STAGE30_11_6_FORBIDDEN_SURFACES,
    STAGE30_11_6_HARVEST_DECISIONS,
    STAGE30_11_6_HARVEST_OUTCOME_FIELDS,
    STAGE30_11_6_HARVEST_PASS_DECISION,
    STAGE30_11_6_HARVEST_REASONS,
    STAGE30_11_6_HARVEST_RESULT_FIELDS,
    STAGE30_11_6_HARVEST_SUMMARY_FIELDS,
    STAGE30_11_6_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_6_MAX_HARVEST_HARD_CAP,
    STAGE30_11_6_MINOR_VERSION,
    STAGE30_11_6_NEXT_ALLOWED_STAGE,
    STAGE30_11_6_NOT_PROJECTED,
    STAGE30_11_6_OPTIONAL_PROJECTION_FIELDS,
    STAGE30_11_6_PROJECTION_DECISIONS,
    STAGE30_11_6_PROJECTION_FIELDS,
    STAGE30_11_6_PROJECTION_PASS_DECISION,
    STAGE30_11_6_PROJECTION_REASONS,
    STAGE30_11_6_PROJECTION_RESULT_FIELDS,
    STAGE30_11_6_REQUIRED_PROJECTION_FIELDS,
    STAGE30_11_6_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME,
    STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_MODULE,
    STAGE30_11_6_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE,
    STAGE30_11_6_TEST_BASENAMES,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_PLANNED_SUBSTAGES,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_6_candidate_source_models import (
    STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_6_HARVEST_DECISIONS as MODELS_HARVEST_DECISIONS,
    STAGE30_11_6_HARVEST_REASONS as MODELS_HARVEST_REASONS,
    STAGE30_11_6_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_11_6_PROJECTION_DECISIONS as MODELS_PROJECTION_DECISIONS,
    STAGE30_11_6_PROJECTION_FIELDS as MODELS_PROJECTION_FIELDS,
    STAGE30_11_6_PROJECTION_REASONS as MODELS_PROJECTION_REASONS,
    candidate_harvest_outcome_field_names,
    candidate_projection_field_names,
    candidate_projection_result_field_names,
    harvest_result_field_names,
    harvest_summary_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor + schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_6_MINOR_VERSION == "30.11.6"
    assert STAGE30_11_6_MINOR_VERSION == MODELS_MINOR_VERSION


def test_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION == (
        "stage30_11_6_v0_candidate_source"
    )
    assert STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_allowed_and_scanned_basenames_are_the_four_modules() -> None:
    expected = (
        STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME,
        STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME,
        STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME,
        STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_BASENAME,
    )
    assert STAGE30_11_6_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_6_SCANNED_PRODUCTION_BASENAMES == expected


def test_basenames_pinned() -> None:
    assert STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME == (
        "stage30_11_6_candidate_source_models.py"
    )
    assert STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME == (
        "stage30_11_6_stage29_projection_adapter.py"
    )
    assert STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME == (
        "stage30_11_6_candidate_harvest_adapter.py"
    )
    assert STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_BASENAME == (
        "stage30_11_6_fake_candidate_source_proof.py"
    )


def test_module_paths_pinned() -> None:
    assert STAGE30_11_6_CANDIDATE_SOURCE_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_6_candidate_source_models"
    )
    assert STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_6_stage29_projection_adapter"
    )
    assert STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_6_candidate_harvest_adapter"
    )
    assert STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_6_fake_candidate_source_proof"
    )
    assert STAGE30_11_6_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_5_fake_live_wiring_proof"
    )


def test_production_files_exist() -> None:
    for basename in STAGE30_11_6_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.6 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_6_TEST_BASENAMES == (
        "test_stage_30_11_6_candidate_source_models.py",
        "test_stage_30_11_6_stage29_projection_adapter.py",
        "test_stage_30_11_6_candidate_harvest_adapter.py",
        "test_stage_30_11_6_fake_candidate_source_proof.py",
        "test_stage_30_11_6_boundaries.py",
        "test_stage_30_11_6_manifest.py",
    )
    for basename in STAGE30_11_6_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.6 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_6_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    for forbidden in ("os", "json", "pathlib", "sqlite3", "time", "datetime"):
        assert forbidden not in STAGE30_11_6_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_11_6_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_6_CANDIDATE_SOURCE_MODELS_MODULE,
        STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_MODULE,
        STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_MODULE,
        STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_MODULE,
        STAGE30_11_6_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE,
    )
    assert len(STAGE30_11_6_ALLOWED_PHX2_IMPORTS) == 5
    for module in STAGE30_11_6_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_6_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Tokens (mirrored from models)
# ---------------------------------------------------------------------------


def test_projection_tokens_pinned_and_match_models() -> None:
    assert STAGE30_11_6_PROJECTION_DECISIONS == (
        "PROJECTED_LIVE_CANDIDATE",
        "REJECTED_MISSING_REQUIRED_FIELD",
        "REJECTED_INVALID_FIELD_SHAPE",
    )
    assert STAGE30_11_6_PROJECTION_PASS_DECISION == "PROJECTED_LIVE_CANDIDATE"
    assert STAGE30_11_6_PROJECTION_REASONS == (
        "READY_FOR_LIVE_RUNNER",
        "MISSING_REQUIRED_CANDIDATE_FIELD",
        "INVALID_CANDIDATE_FIELD_SHAPE",
    )
    assert STAGE30_11_6_PROJECTION_DECISIONS == MODELS_PROJECTION_DECISIONS
    assert STAGE30_11_6_PROJECTION_REASONS == MODELS_PROJECTION_REASONS


def test_harvest_tokens_pinned_and_match_models() -> None:
    assert STAGE30_11_6_HARVEST_DECISIONS == (
        "HARVESTED_LIVE_CANDIDATE",
        "SKIPPED_ASSEMBLY_FAILED",
        "SKIPPED_PROJECTION_REJECTED",
    )
    assert STAGE30_11_6_HARVEST_PASS_DECISION == "HARVESTED_LIVE_CANDIDATE"
    assert STAGE30_11_6_HARVEST_REASONS == (
        "HARVESTED_READY_FOR_LIVE_RUNNER",
        "ASSEMBLY_RAISED_OR_EMPTY",
        "PROJECTION_FAILED_CLOSED",
    )
    assert STAGE30_11_6_HARVEST_DECISIONS == MODELS_HARVEST_DECISIONS
    assert STAGE30_11_6_HARVEST_REASONS == MODELS_HARVEST_REASONS


def test_not_projected_sentinel_pinned() -> None:
    assert STAGE30_11_6_NOT_PROJECTED == "NOT_PROJECTED"
    assert STAGE30_11_6_NOT_PROJECTED not in STAGE30_11_6_PROJECTION_DECISIONS
    assert STAGE30_11_6_NOT_PROJECTED not in STAGE30_11_6_HARVEST_DECISIONS


# ---------------------------------------------------------------------------
# 5. Field tuples (mirrored from models + cross-checked vs Stage 30.11.5)
# ---------------------------------------------------------------------------


def test_projection_fields_pinned_and_match_models_and_stage_30_11_5() -> None:
    from PHX2.stage30.stage30_11_5_live_wiring_models import (
        STAGE30_11_5_PROJECTION_FIELDS,
    )

    assert STAGE30_11_6_PROJECTION_FIELDS == MODELS_PROJECTION_FIELDS
    assert STAGE30_11_6_PROJECTION_FIELDS == STAGE30_11_5_PROJECTION_FIELDS
    assert "current_market_cap_usd" in STAGE30_11_6_PROJECTION_FIELDS
    assert "tier_hint" in STAGE30_11_6_PROJECTION_FIELDS
    assert len(STAGE30_11_6_REQUIRED_PROJECTION_FIELDS) == 10
    assert STAGE30_11_6_OPTIONAL_PROJECTION_FIELDS == (
        "post_migration_ath_verified",
        "source_ref",
    )


def test_model_field_tuples_pinned_and_match_models() -> None:
    assert STAGE30_11_6_CANDIDATE_PROJECTION_FIELDS == (
        candidate_projection_field_names()
    )
    assert STAGE30_11_6_PROJECTION_RESULT_FIELDS == (
        candidate_projection_result_field_names()
    )
    assert STAGE30_11_6_HARVEST_OUTCOME_FIELDS == (
        candidate_harvest_outcome_field_names()
    )
    assert STAGE30_11_6_HARVEST_SUMMARY_FIELDS == harvest_summary_field_names()
    assert STAGE30_11_6_HARVEST_RESULT_FIELDS == harvest_result_field_names()


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        STAGE30_11_6_CANDIDATE_PROJECTION_FIELDS
        + STAGE30_11_6_PROJECTION_RESULT_FIELDS
        + STAGE30_11_6_HARVEST_OUTCOME_FIELDS
        + STAGE30_11_6_HARVEST_SUMMARY_FIELDS
        + STAGE30_11_6_HARVEST_RESULT_FIELDS
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "web" + "hook",
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
                f"Stage 30.11.6 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. Hard cap + default + prefix
# ---------------------------------------------------------------------------


def test_hard_cap_and_default_and_prefix_pinned() -> None:
    assert STAGE30_11_6_MAX_HARVEST_HARD_CAP == 10
    assert STAGE30_11_6_DEFAULT_MAX_HARVEST == 10
    assert STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX == "stage30_11_6_cand_"


# ---------------------------------------------------------------------------
# 7. Expected proof counts (pinned + cross-checked vs the fake proof)
# ---------------------------------------------------------------------------


def test_expected_counts_pinned() -> None:
    assert STAGE30_11_6_EXPECTED_EVENTS_SEEN == 5
    assert STAGE30_11_6_EXPECTED_HARVESTED == 3
    assert STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED == 1
    assert STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED == 1
    assert STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN == 3
    assert STAGE30_11_6_EXPECTED_RUNNER_BRIDGED == 2
    assert STAGE30_11_6_EXPECTED_RUNNER_GATE_PASSED == 1
    assert STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ATTEMPTED == 1
    assert STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ACCEPTED == 1
    assert STAGE30_11_6_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert STAGE30_11_6_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID == "stage30_11_6_cand_000002"
    assert STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT == "mint-tier1"


def test_expected_counts_match_the_fake_proof() -> None:
    from PHX2.stage30.stage30_11_6_fake_candidate_source_proof import (
        run_stage30_11_6_fake_candidate_source_proof,
    )

    harvest_result, runner_result, client, assembler = (
        run_stage30_11_6_fake_candidate_source_proof()
    )
    h = harvest_result.summary
    assert h.events_seen == STAGE30_11_6_EXPECTED_EVENTS_SEEN
    assert h.harvested == STAGE30_11_6_EXPECTED_HARVESTED
    assert h.skipped_assembly_failed == (
        STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED
    )
    assert h.skipped_projection_rejected == (
        STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED
    )
    r = runner_result.summary
    assert r.candidates_seen == STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN
    assert r.bridged == STAGE30_11_6_EXPECTED_RUNNER_BRIDGED
    assert r.gate_passed == STAGE30_11_6_EXPECTED_RUNNER_GATE_PASSED
    assert r.dispatch_attempted == (
        STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ATTEMPTED
    )
    assert r.dispatch_accepted == (
        STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ACCEPTED
    )
    assert client.attempted == STAGE30_11_6_EXPECTED_TRANSPORT_ATTEMPTS
    assert client.accepted == STAGE30_11_6_EXPECTED_TRANSPORT_ACCEPTS
    assert client.candidate_ids == [STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID]
    assert client.token_mints == [STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT]
    # The old ungated dispatch path was never invoked.
    assert assembler.dispatch_tripwire_calls == 0


# ---------------------------------------------------------------------------
# 8. Next allowed step + family pointer + earlier scoped pointers unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_step_is_the_operator_authorized_ceremony() -> None:
    assert STAGE30_11_6_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert "30.11.7" not in STAGE30_11_6_NEXT_ALLOWED_STAGE
    # The Stage 30.11.5 scoped pointer + the family pointer survive unchanged.
    assert STAGE30_11_5_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


def test_planned_substages_unchanged() -> None:
    # The Stage 30.11.6 manifest edit is additive: the family planned-substage
    # tuple still stops at 30.11.4 (it described the original plan); the 30.11.6
    # slice is admitted via its own scoped constants.
    assert STAGE30_11_PLANNED_SUBSTAGES == (
        "30.11.0",
        "30.11.1",
        "30.11.2",
        "30.11.3",
        "30.11.4",
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_6_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 9. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_6_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_6_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_6_FORBIDDEN_SURFACES)
    for token in (
        "controlled live ceremony executed in this stage",
        "real candidate source binding",
        "real transport call",
        "real Discord send",
        "Discord send",
        "real dispatch reservation",
        "old ungated dispatch invoked",
        "Stage 28.9 live provider session call",
        "ungated Stage 29.3 send path reused directly",
        "live run",
        "live provider call",
        "env read",
        "wall-clock read",
        "new live runner",
        "new broad live runner",
        "bypass Stage 30.11.5 bounded runner",
        "bypass Stage 30.9.3 dip gate",
        "max_harvest above 10",
        "daemon",
        "unbounded loop",
        "Stage 27 / 28 / 29 candidate-record import",
        "database implementation",
        "public routing",
        "subscriber routing",
        "Telegram",
        "wallet / signing",
        "enforcement activation",
        "commit",
        "tag",
        "push",
        "Stage 30.11.7+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.6 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 10. Manifest __all__ exports the Stage 30.11.6 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_6_surface() -> None:
    for name in (
        "STAGE30_11_6_MINOR_VERSION",
        "STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION",
        "STAGE30_11_6_SOURCE_STAGE",
        "STAGE30_11_6_CANDIDATE_SOURCE_MODELS_MODULE",
        "STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_MODULE",
        "STAGE30_11_6_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE",
        "STAGE30_11_6_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_6_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_6_TEST_BASENAMES",
        "STAGE30_11_6_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_6_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_6_PROJECTION_DECISIONS",
        "STAGE30_11_6_HARVEST_DECISIONS",
        "STAGE30_11_6_NOT_PROJECTED",
        "STAGE30_11_6_PROJECTION_FIELDS",
        "STAGE30_11_6_HARVEST_SUMMARY_FIELDS",
        "STAGE30_11_6_MAX_HARVEST_HARD_CAP",
        "STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX",
        "STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID",
        "STAGE30_11_6_NEXT_ALLOWED_STAGE",
        "STAGE30_11_6_FORBIDDEN_SURFACES",
        "STAGE30_11_6_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_6_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_through_30_11_5_constants_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_1_MINOR_VERSION",
        "STAGE30_11_2_MINOR_VERSION",
        "STAGE30_11_3_MINOR_VERSION",
        "STAGE30_11_4_MINOR_VERSION",
        "STAGE30_11_5_MINOR_VERSION",
        "STAGE30_11_5_NEXT_ALLOWED_STAGE",
        "STAGE30_11_5_ALLOWED_STAGE30_BASENAMES",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 11. Stage 30.11.7+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_7_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_6_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_6_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 7:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.6 inventory must not admit a Stage 30.11.7+ file yet; "
        f"saw {violations!r}"
    )
