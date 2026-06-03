"""Stage 30.11.4 manifest pin tests.

Pins the Stage 30.11.4 manifest constants (minor version, end-to-end proof schema
version, the two production basenames + module paths, the committed composed
sibling module paths, the inventory + scanned basenames, the test basenames, the
stdlib + PHX2 import allowlists, the proof decision / reason tokens, the summary /
result field names, the expected proof counts, the operator-authorized next-step
token, the slice forbidden surfaces, the operator-auth live-ceremony note),
asserts the production + test files exist, cross-checks the mirrored schema
version + decision / reason tokens + field names against the Stage 30.11.4 models
module, cross-checks the expected counts against the proof, confirms the Stage
30.11.0 / 30.11.1 / 30.11.2 / 30.11.3 constants + planned substages + family
next-allowed pointer survive unchanged, and pins the Stage 30.11.5+ / Stage 31
future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_1_NEXT_ALLOWED_STAGE,
    STAGE30_11_2_NEXT_ALLOWED_STAGE,
    STAGE30_11_3_NEXT_ALLOWED_STAGE,
    STAGE30_11_4_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_4_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_4_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES,
    STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED,
    STAGE30_11_4_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_4_EXPECTED_GATE_PASSES,
    STAGE30_11_4_EXPECTED_GATE_SUPPRESSED,
    STAGE30_11_4_EXPECTED_SINK_ACCEPTS,
    STAGE30_11_4_EXPECTED_SINK_ATTEMPTS,
    STAGE30_11_4_EXPECTED_SINK_FAILURES,
    STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS,
    STAGE30_11_4_FORBIDDEN_SURFACES,
    STAGE30_11_4_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_4_MINOR_VERSION,
    STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_4_NEXT_ALLOWED_STAGE,
    STAGE30_11_4_OFFLINE_E2E_PROOF_BASENAME,
    STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_BASENAME,
    STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_MODULE,
    STAGE30_11_4_OFFLINE_E2E_PROOF_MODULE,
    STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION,
    STAGE30_11_4_PROOF_DECISIONS,
    STAGE30_11_4_PROOF_PASS_DECISION,
    STAGE30_11_4_PROOF_PASS_REASON,
    STAGE30_11_4_PROOF_REASONS,
    STAGE30_11_4_PROOF_RESULT_FIELDS,
    STAGE30_11_4_PROOF_SUMMARY_FIELDS,
    STAGE30_11_4_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_4_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
    STAGE30_11_4_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_4_STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE,
    STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
    STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
    STAGE30_11_4_TEST_BASENAMES,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_PLANNED_SUBSTAGES,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_4_offline_e2e_proof_models import (
    STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES as MODELS_BRIDGE_SUCCESSES,
    STAGE30_11_4_EXPECTED_CANDIDATES_SEEN as MODELS_CANDIDATES_SEEN,
    STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID as MODELS_DIP_CANDIDATE_ID,
    STAGE30_11_4_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_4_PROOF_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_4_PROOF_PASS_DECISION as MODELS_PASS_DECISION,
    STAGE30_11_4_PROOF_PASS_REASON as MODELS_PASS_REASON,
    STAGE30_11_4_PROOF_REASONS as MODELS_REASONS,
    offline_e2e_proof_result_field_names,
    offline_e2e_proof_summary_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_4_MINOR_VERSION == "30.11.4"
    assert STAGE30_11_4_MINOR_VERSION == MODELS_MINOR_VERSION


def test_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION == (
        "stage30_11_4_v0_offline_e2e_proof"
    )
    assert STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_BASENAME == (
        "stage30_11_4_offline_e2e_proof_models.py"
    )
    assert STAGE30_11_4_OFFLINE_E2E_PROOF_BASENAME == (
        "stage30_11_4_offline_e2e_proof.py"
    )
    assert STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_4_offline_e2e_proof_models"
    )
    assert STAGE30_11_4_OFFLINE_E2E_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_4_offline_e2e_proof"
    )


def test_composed_sibling_modules_pinned() -> None:
    assert STAGE30_11_4_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE == (
        "PHX2.stage30.stage30_11_2_runtime_gate_seam"
    )
    assert STAGE30_11_4_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_2_fake_runtime_gate_proof"
    )
    assert STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_3_private_sink_models"
    )
    assert STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_3_private_sink_adapter"
    )
    assert STAGE30_11_4_STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_3_fake_private_sink_proof"
    )


def test_allowed_and_scanned_basenames_are_the_two_modules() -> None:
    expected = (
        STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_BASENAME,
        STAGE30_11_4_OFFLINE_E2E_PROOF_BASENAME,
    )
    assert STAGE30_11_4_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_4_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_4_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.4 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_4_TEST_BASENAMES == (
        "test_stage_30_11_4_offline_e2e_proof_models.py",
        "test_stage_30_11_4_offline_e2e_proof.py",
        "test_stage_30_11_4_boundaries.py",
        "test_stage_30_11_4_manifest.py",
    )
    for basename in STAGE30_11_4_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.4 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_4_ALLOWED_STDLIB_IMPORTS == (
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
        assert forbidden not in STAGE30_11_4_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_11_4_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_MODULE,
        STAGE30_11_4_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
        STAGE30_11_4_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
        STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
        STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
        STAGE30_11_4_STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE,
    )
    for module in STAGE30_11_4_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_4_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Proof decisions + reasons (mirrored from models)
# ---------------------------------------------------------------------------


def test_proof_decisions_pinned_and_match_models() -> None:
    assert STAGE30_11_4_PROOF_DECISIONS == (
        "OFFLINE_E2E_PROOF_PASSED",
        "OFFLINE_E2E_PROOF_FAILED",
    )
    assert STAGE30_11_4_PROOF_PASS_DECISION == "OFFLINE_E2E_PROOF_PASSED"
    assert STAGE30_11_4_PROOF_DECISIONS == MODELS_DECISIONS
    assert STAGE30_11_4_PROOF_PASS_DECISION == MODELS_PASS_DECISION


def test_proof_reasons_pinned_and_match_models() -> None:
    assert STAGE30_11_4_PROOF_REASONS == (
        "PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY",
        "UNEXPECTED_E2E_COUNTS",
        "UNEXPECTED_TRANSPORT_ATTEMPT",
        "INVALID_PROOF_INPUT",
    )
    assert STAGE30_11_4_PROOF_PASS_REASON == (
        "PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY"
    )
    assert STAGE30_11_4_PROOF_REASONS == MODELS_REASONS
    assert STAGE30_11_4_PROOF_PASS_REASON == MODELS_PASS_REASON


# ---------------------------------------------------------------------------
# 5. Field-name tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_summary_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_4_PROOF_SUMMARY_FIELDS == (
        "candidates_seen",
        "bridge_successes",
        "bridge_suppressed",
        "gate_passes",
        "gate_suppressed",
        "sink_attempts",
        "sink_accepts",
        "sink_failures",
        "transport_attempts",
        "transport_accepts",
        "runtime_stopped_by_candidate_cap",
        "runtime_stopped_by_dispatch_cap",
        "runtime_stopped_by_runtime_seconds",
        "proof_decision",
        "proof_reason",
        "created_at_utc",
    )
    assert STAGE30_11_4_PROOF_SUMMARY_FIELDS == (
        offline_e2e_proof_summary_field_names()
    )


def test_result_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_4_PROOF_RESULT_FIELDS == (
        "proof_decision",
        "proof_reason",
        "summary",
        "runtime_outcomes",
        "transport_candidate_ids",
        "transport_token_mints",
        "created_at_utc",
    )
    assert STAGE30_11_4_PROOF_RESULT_FIELDS == (
        offline_e2e_proof_result_field_names()
    )


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        STAGE30_11_4_PROOF_SUMMARY_FIELDS + STAGE30_11_4_PROOF_RESULT_FIELDS
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
                f"Stage 30.11.4 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. Expected proof counts (mirrored from models + cross-checked vs proof)
# ---------------------------------------------------------------------------


def test_expected_counts_pinned_and_match_models() -> None:
    assert STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN == 4
    assert STAGE30_11_4_EXPECTED_CANDIDATES_SEEN == 5
    assert STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES == 2
    assert STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED == 3
    assert STAGE30_11_4_EXPECTED_GATE_PASSES == 1
    assert STAGE30_11_4_EXPECTED_GATE_SUPPRESSED == 1
    assert STAGE30_11_4_EXPECTED_SINK_ATTEMPTS == 1
    assert STAGE30_11_4_EXPECTED_SINK_ACCEPTS == 1
    assert STAGE30_11_4_EXPECTED_SINK_FAILURES == 0
    assert STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID == "cand-tier1"
    assert STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT == "mint-tier1"
    # A sample of the count mirrors against the models module.
    assert STAGE30_11_4_EXPECTED_CANDIDATES_SEEN == MODELS_CANDIDATES_SEEN
    assert STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES == MODELS_BRIDGE_SUCCESSES
    assert STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID == MODELS_DIP_CANDIDATE_ID


def test_expected_counts_match_the_proof() -> None:
    from PHX2.stage30.stage30_11_4_offline_e2e_proof import (
        run_stage30_11_4_offline_e2e_proof,
    )

    result = run_stage30_11_4_offline_e2e_proof()
    summary = result.summary
    assert result.proof_decision == STAGE30_11_4_PROOF_PASS_DECISION
    assert result.proof_reason == STAGE30_11_4_PROOF_PASS_REASON
    assert summary.candidates_seen == STAGE30_11_4_EXPECTED_CANDIDATES_SEEN
    assert summary.bridge_successes == STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES
    assert summary.bridge_suppressed == STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED
    assert summary.gate_passes == STAGE30_11_4_EXPECTED_GATE_PASSES
    assert summary.gate_suppressed == STAGE30_11_4_EXPECTED_GATE_SUPPRESSED
    assert summary.sink_attempts == STAGE30_11_4_EXPECTED_SINK_ATTEMPTS
    assert summary.sink_accepts == STAGE30_11_4_EXPECTED_SINK_ACCEPTS
    assert summary.sink_failures == STAGE30_11_4_EXPECTED_SINK_FAILURES
    assert summary.transport_attempts == (
        STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS
    )
    assert summary.transport_accepts == STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS
    assert result.transport_candidate_ids == (
        STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID,
    )
    assert result.transport_token_mints == (
        STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT,
    )


# ---------------------------------------------------------------------------
# 7. Next allowed step + family pointer + planned substages unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_step_is_the_operator_authorized_ceremony() -> None:
    # The 30.11.4-scoped pointer names the operator-authorized controlled live
    # ceremony (NOT a further Stage 30.11.<N> implementation slice). The Stage
    # 30.11.0 family pointer stays pinned at 30.11.1 and the earlier scoped
    # pointers survive.
    assert STAGE30_11_4_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    # The next step is not a numbered substage.
    assert "30.11.5" not in STAGE30_11_4_NEXT_ALLOWED_STAGE
    assert STAGE30_11_3_NEXT_ALLOWED_STAGE == "30.11.4"
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
    assert STAGE30_11_PLANNED_SUBSTAGES[-1] == "30.11.4"
    joined = " ".join(STAGE30_11_PLANNED_SUBSTAGES)
    assert "30.11.5" not in joined
    assert "30.12" not in joined
    assert "31" not in joined


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_4_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 8. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_4_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_4_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_4_FORBIDDEN_SURFACES)
    for token in (
        "controlled live ceremony executed in this stage",
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
        "new readiness gate",
        "new runtime gate seam",
        "new private sink adapter",
        "new dip gate",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "daemon",
        "background service",
        "autorestart loop",
        "unbounded loop",
        "Stage 28 transport-internals edit",
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
        "Stage 30.11.5+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.4 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 9. Manifest __all__ exports the Stage 30.11.4 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_4_surface() -> None:
    for name in (
        "STAGE30_11_4_MINOR_VERSION",
        "STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION",
        "STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_BASENAME",
        "STAGE30_11_4_OFFLINE_E2E_PROOF_BASENAME",
        "STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_MODULE",
        "STAGE30_11_4_OFFLINE_E2E_PROOF_MODULE",
        "STAGE30_11_4_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE",
        "STAGE30_11_4_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE",
        "STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE",
        "STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE",
        "STAGE30_11_4_STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE",
        "STAGE30_11_4_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_4_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_4_TEST_BASENAMES",
        "STAGE30_11_4_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_4_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_4_PROOF_DECISIONS",
        "STAGE30_11_4_PROOF_PASS_DECISION",
        "STAGE30_11_4_PROOF_REASONS",
        "STAGE30_11_4_PROOF_PASS_REASON",
        "STAGE30_11_4_PROOF_SUMMARY_FIELDS",
        "STAGE30_11_4_PROOF_RESULT_FIELDS",
        "STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN",
        "STAGE30_11_4_EXPECTED_CANDIDATES_SEEN",
        "STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES",
        "STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED",
        "STAGE30_11_4_EXPECTED_GATE_PASSES",
        "STAGE30_11_4_EXPECTED_GATE_SUPPRESSED",
        "STAGE30_11_4_EXPECTED_SINK_ATTEMPTS",
        "STAGE30_11_4_EXPECTED_SINK_ACCEPTS",
        "STAGE30_11_4_EXPECTED_SINK_FAILURES",
        "STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS",
        "STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS",
        "STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID",
        "STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT",
        "STAGE30_11_4_NEXT_ALLOWED_STAGE",
        "STAGE30_11_4_NEXT_ALLOWED_STAGE_TITLE",
        "STAGE30_11_4_FORBIDDEN_SURFACES",
        "STAGE30_11_4_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_4_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_through_30_11_3_constants_still_present() -> None:
    # The Stage 30.11.4 manifest edit is purely additive: the Stage 30.11.0 /
    # 30.11.1 / 30.11.2 / 30.11.3 constants survive.
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_FORBIDDEN_SURFACES",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_11_1_MINOR_VERSION",
        "STAGE30_11_1_NEXT_ALLOWED_STAGE",
        "STAGE30_11_2_MINOR_VERSION",
        "STAGE30_11_2_NEXT_ALLOWED_STAGE",
        "STAGE30_11_3_MINOR_VERSION",
        "STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION",
        "STAGE30_11_3_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_3_TEST_BASENAMES",
        "STAGE30_11_3_NEXT_ALLOWED_STAGE",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 10. Stage 30.11.5+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_5_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_4_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_4_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 5:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.4 inventory must not admit a Stage 30.11.5+ file yet; "
        f"saw {violations!r}"
    )
