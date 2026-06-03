"""Stage 30.11.7 manifest pin tests.

Pins the Stage 30.11.7 manifest constants (minor version, enrichment schema
version, the three production basenames + module paths, the test-composed committed
runner module, the inventory + scanned + test basenames, the stdlib + PHX2 import
allowlists, the enrichment decision / reason / dimension tokens, the enriched +
model + resolver field names, the PRESENT token + hard cap + default, the expected
proof counts, the operator-authorized next-step token, the slice forbidden surfaces,
the operator-auth live-ceremony note), asserts the files exist, cross-checks the
mirrored schema version + tokens + field names against the Stage 30.11.7 models
module, cross-checks the expected counts against the fake proof + the committed
runner, confirms the Stage 30.11.0..30.11.6 constants + family next-allowed pointer
survive unchanged, and pins the Stage 30.11.8+ / Stage 31 future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_6_NEXT_ALLOWED_STAGE,
    STAGE30_11_7_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_7_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_7_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_7_ATH_RESOLUTION_FIELDS,
    STAGE30_11_7_CONTEXT_STATUS_PRESENT,
    STAGE30_11_7_DEFAULT_MAX_ENRICH,
    STAGE30_11_7_ENRICHED_FIELDS,
    STAGE30_11_7_ENRICHMENT_ADAPTER_BASENAME,
    STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE,
    STAGE30_11_7_ENRICHMENT_DECISIONS,
    STAGE30_11_7_ENRICHMENT_DIMENSIONS,
    STAGE30_11_7_ENRICHMENT_MODELS_BASENAME,
    STAGE30_11_7_ENRICHMENT_MODELS_MODULE,
    STAGE30_11_7_ENRICHMENT_PASS_DECISION,
    STAGE30_11_7_ENRICHMENT_PASS_REASON,
    STAGE30_11_7_ENRICHMENT_REASONS,
    STAGE30_11_7_ENRICHMENT_RESULT_FIELDS,
    STAGE30_11_7_ENRICHMENT_RUN_RESULT_FIELDS,
    STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION,
    STAGE30_11_7_ENRICHMENT_SUMMARY_FIELDS,
    STAGE30_11_7_EXPECTED_BASES_SEEN,
    STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_7_EXPECTED_ENRICHED,
    STAGE30_11_7_EXPECTED_REJECTED_ATH,
    STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT,
    STAGE30_11_7_EXPECTED_REJECTED_MIGRATION,
    STAGE30_11_7_EXPECTED_REJECTED_TIER,
    STAGE30_11_7_EXPECTED_RUNNER_BRIDGED,
    STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN,
    STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED,
    STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS,
    STAGE30_11_7_FAKE_ENRICHMENT_PROOF_BASENAME,
    STAGE30_11_7_FAKE_ENRICHMENT_PROOF_MODULE,
    STAGE30_11_7_FORBIDDEN_SURFACES,
    STAGE30_11_7_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_7_MARKET_CONTEXT_RESOLUTION_FIELDS,
    STAGE30_11_7_MAX_ENRICH_HARD_CAP,
    STAGE30_11_7_MIGRATION_RESOLUTION_FIELDS,
    STAGE30_11_7_MINOR_VERSION,
    STAGE30_11_7_NEXT_ALLOWED_STAGE,
    STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS,
    STAGE30_11_7_REQUIRED_ENRICHED_FIELDS,
    STAGE30_11_7_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_7_TEST_BASENAMES,
    STAGE30_11_7_TEST_COMPOSES_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE,
    STAGE30_11_7_TIER_RESOLUTION_FIELDS,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    STAGE30_11_7_ENRICHMENT_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_7_ENRICHMENT_DIMENSIONS as MODELS_DIMENSIONS,
    STAGE30_11_7_ENRICHMENT_REASONS as MODELS_REASONS,
    STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_7_MINOR_VERSION as MODELS_MINOR_VERSION,
    ath_resolution_field_names,
    enriched_candidate_field_names,
    enrichment_result_field_names,
    enrichment_run_result_field_names,
    enrichment_summary_field_names,
    market_context_resolution_field_names,
    migration_resolution_field_names,
    tier_resolution_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor + schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_7_MINOR_VERSION == "30.11.7"
    assert STAGE30_11_7_MINOR_VERSION == MODELS_MINOR_VERSION


def test_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION == (
        "stage30_11_7_v0_candidate_enrichment"
    )
    assert STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_7_ENRICHMENT_MODELS_BASENAME,
        STAGE30_11_7_ENRICHMENT_ADAPTER_BASENAME,
        STAGE30_11_7_FAKE_ENRICHMENT_PROOF_BASENAME,
    )
    assert STAGE30_11_7_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_7_SCANNED_PRODUCTION_BASENAMES == expected


def test_basenames_pinned() -> None:
    assert STAGE30_11_7_ENRICHMENT_MODELS_BASENAME == (
        "stage30_11_7_candidate_enrichment_models.py"
    )
    assert STAGE30_11_7_ENRICHMENT_ADAPTER_BASENAME == (
        "stage30_11_7_candidate_enrichment_adapter.py"
    )
    assert STAGE30_11_7_FAKE_ENRICHMENT_PROOF_BASENAME == (
        "stage30_11_7_fake_enrichment_proof.py"
    )


def test_module_paths_pinned() -> None:
    assert STAGE30_11_7_ENRICHMENT_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_7_candidate_enrichment_models"
    )
    assert STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_7_candidate_enrichment_adapter"
    )
    assert STAGE30_11_7_FAKE_ENRICHMENT_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_7_fake_enrichment_proof"
    )
    assert STAGE30_11_7_TEST_COMPOSES_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_5_fake_live_wiring_proof"
    )


def test_production_and_test_files_exist() -> None:
    for basename in STAGE30_11_7_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file()
    assert STAGE30_11_7_TEST_BASENAMES == (
        "test_stage_30_11_7_candidate_enrichment_models.py",
        "test_stage_30_11_7_candidate_enrichment_adapter.py",
        "test_stage_30_11_7_fake_enrichment_proof.py",
        "test_stage_30_11_7_boundaries.py",
        "test_stage_30_11_7_manifest.py",
    )
    for basename in STAGE30_11_7_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file()


# ---------------------------------------------------------------------------
# 3. Import allowlists (the slice is a LEAF)
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_7_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    for forbidden in ("os", "json", "pathlib", "sqlite3", "time", "datetime"):
        assert forbidden not in STAGE30_11_7_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_exactly_the_three_own_siblings() -> None:
    assert STAGE30_11_7_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_7_ENRICHMENT_MODELS_MODULE,
        STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE,
        STAGE30_11_7_FAKE_ENRICHMENT_PROOF_MODULE,
    )
    assert len(STAGE30_11_7_ALLOWED_PHX2_IMPORTS) == 3
    # A clean leaf: NO Stage 30.11.5 / Stage 30.11.6 module in the production
    # allowlist (the committed runner is composed by the test only).
    for module in STAGE30_11_7_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_11_7_")
    joined = " ".join(STAGE30_11_7_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Tokens (mirrored from models)
# ---------------------------------------------------------------------------


def test_enrichment_tokens_pinned_and_match_models() -> None:
    assert STAGE30_11_7_ENRICHMENT_DECISIONS == (
        "ENRICHED_DIP_CANDIDATE",
        "REJECTED_ENRICHMENT",
    )
    assert STAGE30_11_7_ENRICHMENT_PASS_DECISION == "ENRICHED_DIP_CANDIDATE"
    assert STAGE30_11_7_ENRICHMENT_REASONS == (
        "READY_FOR_LIVE_RUNNER",
        "MISSING_MARKET_CONTEXT",
        "INVALID_MARKET_CAP",
        "MISSING_TIER",
        "MISSING_MIGRATION_EVIDENCE",
        "UNCONFIRMED_MIGRATION",
        "MISSING_ATH",
        "STALE_ATH",
        "PRE_MIGRATION_ATH_NOT_VERIFIED",
        "INVALID_DRAWDOWN",
    )
    assert STAGE30_11_7_ENRICHMENT_PASS_REASON == "READY_FOR_LIVE_RUNNER"
    assert STAGE30_11_7_ENRICHMENT_DIMENSIONS == (
        "MARKET_CONTEXT",
        "TIER",
        "MIGRATION",
        "ATH",
    )
    assert STAGE30_11_7_ENRICHMENT_DECISIONS == MODELS_DECISIONS
    assert STAGE30_11_7_ENRICHMENT_REASONS == MODELS_REASONS
    assert STAGE30_11_7_ENRICHMENT_DIMENSIONS == MODELS_DIMENSIONS


# ---------------------------------------------------------------------------
# 5. Field tuples (mirrored from models + cross-checked vs Stage 30.11.6)
# ---------------------------------------------------------------------------


def test_enriched_fields_pinned_and_match_models_and_stage_30_11_6() -> None:
    from PHX2.stage30.stage30_11_6_candidate_source_models import (
        STAGE30_11_6_PROJECTION_FIELDS,
    )

    assert STAGE30_11_7_ENRICHED_FIELDS == enriched_candidate_field_names()
    assert STAGE30_11_7_ENRICHED_FIELDS == STAGE30_11_6_PROJECTION_FIELDS
    assert "current_market_cap_usd" in STAGE30_11_7_ENRICHED_FIELDS
    assert "tier_hint" in STAGE30_11_7_ENRICHED_FIELDS
    assert len(STAGE30_11_7_REQUIRED_ENRICHED_FIELDS) == 10
    assert STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS == (
        "post_migration_ath_verified",
        "source_ref",
    )


def test_model_and_resolver_field_tuples_match_models() -> None:
    assert STAGE30_11_7_ENRICHMENT_RESULT_FIELDS == (
        enrichment_result_field_names()
    )
    assert STAGE30_11_7_ENRICHMENT_SUMMARY_FIELDS == (
        enrichment_summary_field_names()
    )
    assert STAGE30_11_7_ENRICHMENT_RUN_RESULT_FIELDS == (
        enrichment_run_result_field_names()
    )
    assert STAGE30_11_7_MARKET_CONTEXT_RESOLUTION_FIELDS == (
        market_context_resolution_field_names()
    )
    assert STAGE30_11_7_TIER_RESOLUTION_FIELDS == tier_resolution_field_names()
    assert STAGE30_11_7_MIGRATION_RESOLUTION_FIELDS == (
        migration_resolution_field_names()
    )
    assert STAGE30_11_7_ATH_RESOLUTION_FIELDS == ath_resolution_field_names()


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        STAGE30_11_7_ENRICHED_FIELDS
        + STAGE30_11_7_ENRICHMENT_RESULT_FIELDS
        + STAGE30_11_7_ENRICHMENT_SUMMARY_FIELDS
        + STAGE30_11_7_ENRICHMENT_RUN_RESULT_FIELDS
        + STAGE30_11_7_MARKET_CONTEXT_RESOLUTION_FIELDS
        + STAGE30_11_7_TIER_RESOLUTION_FIELDS
        + STAGE30_11_7_MIGRATION_RESOLUTION_FIELDS
        + STAGE30_11_7_ATH_RESOLUTION_FIELDS
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
                f"Stage 30.11.7 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. PRESENT token + hard cap + default
# ---------------------------------------------------------------------------


def test_present_token_cap_and_default_pinned() -> None:
    assert STAGE30_11_7_CONTEXT_STATUS_PRESENT == "PRESENT"
    assert STAGE30_11_7_MAX_ENRICH_HARD_CAP == 10
    assert STAGE30_11_7_DEFAULT_MAX_ENRICH == 10


# ---------------------------------------------------------------------------
# 7. Expected proof counts (pinned + cross-checked vs the fake proof + runner)
# ---------------------------------------------------------------------------


def test_expected_counts_pinned() -> None:
    assert STAGE30_11_7_EXPECTED_BASES_SEEN == 6
    assert STAGE30_11_7_EXPECTED_ENRICHED == 2
    assert STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT == 1
    assert STAGE30_11_7_EXPECTED_REJECTED_TIER == 1
    assert STAGE30_11_7_EXPECTED_REJECTED_MIGRATION == 1
    assert STAGE30_11_7_EXPECTED_REJECTED_ATH == 1
    assert STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN == 2
    assert STAGE30_11_7_EXPECTED_RUNNER_BRIDGED == 2
    assert STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED == 1
    assert STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID == "stage30_11_7_cand_dip"
    assert STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT == "mint-dip"


def test_expected_counts_match_the_fake_proof_and_runner() -> None:
    from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
        run_stage30_11_5_fake_live_wiring_proof,
    )
    from PHX2.stage30.stage30_11_7_fake_enrichment_proof import (
        run_stage30_11_7_fake_enrichment,
    )

    run = run_stage30_11_7_fake_enrichment()
    s = run.summary
    assert s.bases_seen == STAGE30_11_7_EXPECTED_BASES_SEEN
    assert s.enriched == STAGE30_11_7_EXPECTED_ENRICHED
    assert s.rejected_market_context == (
        STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT
    )
    assert s.rejected_tier == STAGE30_11_7_EXPECTED_REJECTED_TIER
    assert s.rejected_migration == STAGE30_11_7_EXPECTED_REJECTED_MIGRATION
    assert s.rejected_ath == STAGE30_11_7_EXPECTED_REJECTED_ATH

    result, client = run_stage30_11_5_fake_live_wiring_proof(
        candidate_source=run.candidate_source
    )
    r = result.summary
    assert r.candidates_seen == STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN
    assert r.bridged == STAGE30_11_7_EXPECTED_RUNNER_BRIDGED
    assert r.gate_passed == STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED
    assert client.attempted == STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS
    assert client.accepted == STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS
    assert client.candidate_ids == [STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID]
    assert client.token_mints == [STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT]


# ---------------------------------------------------------------------------
# 8. Next allowed step + family pointer + earlier scoped pointers unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_step_is_the_operator_authorized_ceremony() -> None:
    assert STAGE30_11_7_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert "30.11.8" not in STAGE30_11_7_NEXT_ALLOWED_STAGE
    # The Stage 30.11.6 scoped pointer + the family pointer survive unchanged.
    assert STAGE30_11_6_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_7_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 9. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_7_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_7_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_7_FORBIDDEN_SURFACES)
    for token in (
        "controlled live ceremony executed in this stage",
        "real resolver binding",
        "real transport call",
        "real Discord send",
        "Discord send",
        "real dispatch reservation",
        "old ungated dispatch invoked",
        "ungated Stage 29.3 send path reused directly",
        "live run",
        "live provider call",
        "env read",
        "wall-clock read",
        "new live runner",
        "parallel tier model",
        "fabricate missing dip field",
        "treat UNKNOWN migration as eligible",
        "treat missing or stale market context as eligible",
        "treat missing or stale ATH as eligible",
        "bypass Stage 30.11.5 bounded runner",
        "bypass Stage 30.11.6 harvest projection",
        "bypass Stage 30.9.3 dip gate",
        "max_enrich above 10",
        "daemon",
        "unbounded loop",
        "Stage 30.11.5 / Stage 30.11.6 production import",
        "Stage 25/27/28/29 production import",
        "public routing",
        "subscriber routing",
        "Telegram",
        "wallet / signing",
        "enforcement activation",
        "commit",
        "tag",
        "push",
        "Stage 30.11.8+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.7 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 10. Manifest __all__ exports the Stage 30.11.7 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_7_surface() -> None:
    for name in (
        "STAGE30_11_7_MINOR_VERSION",
        "STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION",
        "STAGE30_11_7_SOURCE_STAGE",
        "STAGE30_11_7_ENRICHMENT_MODELS_MODULE",
        "STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE",
        "STAGE30_11_7_FAKE_ENRICHMENT_PROOF_MODULE",
        "STAGE30_11_7_TEST_COMPOSES_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE",
        "STAGE30_11_7_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_7_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_7_TEST_BASENAMES",
        "STAGE30_11_7_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_7_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_7_ENRICHMENT_DECISIONS",
        "STAGE30_11_7_ENRICHMENT_REASONS",
        "STAGE30_11_7_ENRICHMENT_DIMENSIONS",
        "STAGE30_11_7_ENRICHED_FIELDS",
        "STAGE30_11_7_MAX_ENRICH_HARD_CAP",
        "STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID",
        "STAGE30_11_7_NEXT_ALLOWED_STAGE",
        "STAGE30_11_7_FORBIDDEN_SURFACES",
        "STAGE30_11_7_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_7_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_through_30_11_6_constants_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_5_MINOR_VERSION",
        "STAGE30_11_5_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_6_MINOR_VERSION",
        "STAGE30_11_6_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_6_NEXT_ALLOWED_STAGE",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 11. Stage 30.11.8+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_8_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_7_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_7_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 8:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.7 inventory must not admit a Stage 30.11.8+ file yet; "
        f"saw {violations!r}"
    )
