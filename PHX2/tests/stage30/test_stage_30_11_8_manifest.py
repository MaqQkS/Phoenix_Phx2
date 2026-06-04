"""Stage 30.11.8 manifest pin tests.

Pins the Stage 30.11.8 manifest constants (minor version, confirmation schema
version, the three production basenames + module paths, the test-composed committed
Stage 30.11.7 modules, the inventory + scanned + test basenames, the stdlib + PHX2
import allowlists, the measurement-status / decision / reason vocabularies, the
evidence / resolution / summary / run-result field names, the expected proof counts,
the operator-authorized next-step token, the slice forbidden surfaces, the
operator-auth live-ceremony note), asserts the files exist, cross-checks the
mirrored schema version + tokens + field names against the Stage 30.11.8 models
module, cross-checks the expected counts against the fake proof, confirms the Stage
30.11.0..30.11.7 constants + family next-allowed pointer survive unchanged, and pins
the Stage 30.11.9+ / Stage 31 future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_7_NEXT_ALLOWED_STAGE,
    STAGE30_11_8_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_8_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_8_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_8_CONFIRMATION_ADAPTER_BASENAME,
    STAGE30_11_8_CONFIRMATION_ADAPTER_MODULE,
    STAGE30_11_8_CONFIRMATION_DECISIONS,
    STAGE30_11_8_CONFIRMATION_MODELS_BASENAME,
    STAGE30_11_8_CONFIRMATION_MODELS_MODULE,
    STAGE30_11_8_CONFIRMATION_PASS_DECISION,
    STAGE30_11_8_CONFIRMATION_PASS_REASON,
    STAGE30_11_8_CONFIRMATION_REASONS,
    STAGE30_11_8_CONFIRMATION_RUN_RESULT_FIELDS,
    STAGE30_11_8_CONFIRMATION_SCHEMA_VERSION,
    STAGE30_11_8_CONFIRMATION_SUMMARY_FIELDS,
    STAGE30_11_8_EXPECTED_BASES_SEEN,
    STAGE30_11_8_EXPECTED_CONFIRMED,
    STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT,
    STAGE30_11_8_EXPECTED_UNCONFIRMED,
    STAGE30_11_8_FAKE_CONFIRMATION_PROOF_BASENAME,
    STAGE30_11_8_FAKE_CONFIRMATION_PROOF_MODULE,
    STAGE30_11_8_FORBIDDEN_SURFACES,
    STAGE30_11_8_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
    STAGE30_11_8_MIGRATION_EVIDENCE_FIELDS,
    STAGE30_11_8_MIGRATION_RESOLUTION_FIELDS,
    STAGE30_11_8_MINOR_VERSION,
    STAGE30_11_8_NEXT_ALLOWED_STAGE,
    STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES,
    STAGE30_11_8_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_8_TEST_BASENAMES,
    STAGE30_11_8_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE,
    STAGE30_11_8_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_MODELS_MODULE,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    STAGE30_11_8_CONFIRMATION_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_8_CONFIRMATION_REASONS as MODELS_REASONS,
    STAGE30_11_8_CONFIRMATION_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_8_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES as MODELS_STATUSES,
    confirmation_run_result_field_names,
    confirmation_summary_field_names,
    migration_evidence_field_names,
    migration_resolution_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor + schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_8_MINOR_VERSION == "30.11.8"
    assert STAGE30_11_8_MINOR_VERSION == MODELS_MINOR_VERSION


def test_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_8_CONFIRMATION_SCHEMA_VERSION == (
        "stage30_11_8_v0_migration_confirmation"
    )
    assert STAGE30_11_8_CONFIRMATION_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_8_CONFIRMATION_MODELS_BASENAME,
        STAGE30_11_8_CONFIRMATION_ADAPTER_BASENAME,
        STAGE30_11_8_FAKE_CONFIRMATION_PROOF_BASENAME,
    )
    assert STAGE30_11_8_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_8_SCANNED_PRODUCTION_BASENAMES == expected


def test_basenames_pinned() -> None:
    assert STAGE30_11_8_CONFIRMATION_MODELS_BASENAME == (
        "stage30_11_8_migration_confirmation_models.py"
    )
    assert STAGE30_11_8_CONFIRMATION_ADAPTER_BASENAME == (
        "stage30_11_8_migration_confirmation_adapter.py"
    )
    assert STAGE30_11_8_FAKE_CONFIRMATION_PROOF_BASENAME == (
        "stage30_11_8_fake_confirmation_proof.py"
    )


def test_module_paths_pinned() -> None:
    assert STAGE30_11_8_CONFIRMATION_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_8_migration_confirmation_models"
    )
    assert STAGE30_11_8_CONFIRMATION_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_8_migration_confirmation_adapter"
    )
    assert STAGE30_11_8_FAKE_CONFIRMATION_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_8_fake_confirmation_proof"
    )
    # The committed Stage 30.11.7 modules the TEST composes (NOT production).
    assert STAGE30_11_8_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_7_candidate_enrichment_adapter"
    )
    assert STAGE30_11_8_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_7_candidate_enrichment_models"
    )


def test_production_and_test_files_exist() -> None:
    for basename in STAGE30_11_8_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file()
    assert STAGE30_11_8_TEST_BASENAMES == (
        "test_stage_30_11_8_migration_confirmation_models.py",
        "test_stage_30_11_8_migration_confirmation_adapter.py",
        "test_stage_30_11_8_fake_confirmation_proof.py",
        "test_stage_30_11_8_boundaries.py",
        "test_stage_30_11_8_manifest.py",
    )
    for basename in STAGE30_11_8_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file()


# ---------------------------------------------------------------------------
# 3. Import allowlists (the slice is a LEAF; no broad prefix)
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_8_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "re",
    )
    for forbidden in ("os", "json", "pathlib", "sqlite3", "time", "datetime"):
        assert forbidden not in STAGE30_11_8_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_exactly_the_three_own_siblings() -> None:
    assert STAGE30_11_8_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_8_CONFIRMATION_MODELS_MODULE,
        STAGE30_11_8_CONFIRMATION_ADAPTER_MODULE,
        STAGE30_11_8_FAKE_CONFIRMATION_PROOF_MODULE,
    )
    assert len(STAGE30_11_8_ALLOWED_PHX2_IMPORTS) == 3
    # A clean leaf: every entry is a Stage 30.11.8 module; no Stage 30.11.5 /
    # 30.11.6 / 30.11.7 module, and no bare package prefix.
    for module in STAGE30_11_8_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_11_8_")
    for prefix in ("PHX2.stage30", "PHX2.stage30.stage30_11_8_"):
        assert prefix not in STAGE30_11_8_ALLOWED_PHX2_IMPORTS
    joined = " ".join(STAGE30_11_8_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Tokens (mirrored from models)
# ---------------------------------------------------------------------------


def test_measurement_status_tokens_match_models() -> None:
    assert STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE == "COMPLETE"
    assert STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES == MODELS_STATUSES
    assert STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES == (
        "COMPLETE",
        "PARTIAL_MIGRATION_PRESENT",
        "MISSING_MIGRATION",
        "INVALID_MIGRATION",
        "CONFLICTING_MIGRATION",
    )


def test_confirmation_tokens_pinned_and_match_models() -> None:
    assert STAGE30_11_8_CONFIRMATION_DECISIONS == (
        "CONFIRMED_MIGRATION",
        "UNCONFIRMED_MIGRATION",
    )
    assert STAGE30_11_8_CONFIRMATION_PASS_DECISION == "CONFIRMED_MIGRATION"
    assert STAGE30_11_8_CONFIRMATION_REASONS == (
        "CONFIRMED_ON_CHAIN_EVENT",
        "BLANK_CANDIDATE_MINT",
        "MISSING_MIGRATION_EVIDENCE",
        "EVIDENCE_MINT_MISMATCH",
        "REDACTION_UNSAFE",
        "UNKNOWN_MIGRATION",
        "PARTIAL_MIGRATION_UNVERIFIED",
        "EVIDENCE_REPORTS_NO_MIGRATION",
        "CONTRADICTORY_MIGRATION_EVIDENCE",
        "INVALID_MIGRATION_EVIDENCE",
        "STALE_MIGRATION_EVIDENCE",
        "INVALID_MIGRATION_ANCHOR",
    )
    assert STAGE30_11_8_CONFIRMATION_PASS_REASON == "CONFIRMED_ON_CHAIN_EVENT"
    assert STAGE30_11_8_CONFIRMATION_DECISIONS == MODELS_DECISIONS
    assert STAGE30_11_8_CONFIRMATION_REASONS == MODELS_REASONS


# ---------------------------------------------------------------------------
# 5. Field tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_field_tuples_match_models() -> None:
    assert STAGE30_11_8_MIGRATION_EVIDENCE_FIELDS == (
        migration_evidence_field_names()
    )
    assert STAGE30_11_8_MIGRATION_RESOLUTION_FIELDS == (
        migration_resolution_field_names()
    )
    assert STAGE30_11_8_CONFIRMATION_SUMMARY_FIELDS == (
        confirmation_summary_field_names()
    )
    assert STAGE30_11_8_CONFIRMATION_RUN_RESULT_FIELDS == (
        confirmation_run_result_field_names()
    )
    # The resolution exposes the Stage 30.11.7 migration-resolver result fields.
    assert "confirmed" in STAGE30_11_8_MIGRATION_RESOLUTION_FIELDS
    assert "source_ref" in STAGE30_11_8_MIGRATION_RESOLUTION_FIELDS


# ---------------------------------------------------------------------------
# 6. Expected proof counts (pinned + cross-checked vs the fake proof)
# ---------------------------------------------------------------------------


def test_expected_counts_pinned() -> None:
    assert STAGE30_11_8_EXPECTED_BASES_SEEN == 11
    assert STAGE30_11_8_EXPECTED_CONFIRMED == 1
    assert STAGE30_11_8_EXPECTED_UNCONFIRMED == 10
    assert STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT == "mint-confirmed"


def test_expected_counts_match_the_fake_proof() -> None:
    from PHX2.stage30.stage30_11_8_fake_confirmation_proof import (
        run_stage30_11_8_fake_confirmation,
    )

    run = run_stage30_11_8_fake_confirmation()
    s = run.summary
    assert s.bases_seen == STAGE30_11_8_EXPECTED_BASES_SEEN
    assert s.confirmed == STAGE30_11_8_EXPECTED_CONFIRMED
    assert s.unconfirmed == STAGE30_11_8_EXPECTED_UNCONFIRMED
    confirmed = [o for o in run.outcomes if o.confirmed is True]
    assert len(confirmed) == 1
    assert confirmed[0].token_mint == STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT


# ---------------------------------------------------------------------------
# 7. Next allowed step + family pointer + earlier scoped pointers unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_step_is_the_operator_authorized_ceremony() -> None:
    assert STAGE30_11_8_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert "30.11.9" not in STAGE30_11_8_NEXT_ALLOWED_STAGE
    # The Stage 30.11.7 scoped pointer + the family pointer survive unchanged.
    assert STAGE30_11_7_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_8_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 8. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_8_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_8_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_8_FORBIDDEN_SURFACES)
    for token in (
        "controlled live ceremony executed in this stage",
        "real evidence-source binding",
        "real migration provider call",
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
        "fabricate migration evidence",
        "fabricate migration timestamp",
        "treat UNKNOWN migration as eligible",
        "treat contradictory migration evidence as eligible",
        "treat invalid migration evidence as eligible",
        "treat stale migration evidence as eligible",
        "inherit another mint migration evidence",
        "collapse contradictory or invalid evidence into silent unknown",
        "loosen Stage 30.11.7 enrichment",
        "modify Stage 30.11.7 enrichment",
        "modify Stage 29.3 no-migration-evidence source",
        "bypass Stage 30.11.7 enrichment",
        "bypass Stage 30.11.6 harvest projection",
        "bypass Stage 30.11.5 bounded runner",
        "bypass Stage 30.9.3 dip gate",
        "daemon",
        "unbounded loop",
        "Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 production import",
        "Stage 25/27/28/29 production import",
        "public routing",
        "subscriber routing",
        "Telegram",
        "wallet / signing",
        "enforcement activation",
        "commit",
        "tag",
        "push",
        "Stage 30.11.9+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.8 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 9. Manifest __all__ exports the Stage 30.11.8 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_8_surface() -> None:
    for name in (
        "STAGE30_11_8_MINOR_VERSION",
        "STAGE30_11_8_CONFIRMATION_SCHEMA_VERSION",
        "STAGE30_11_8_SOURCE_STAGE",
        "STAGE30_11_8_CONFIRMATION_MODELS_MODULE",
        "STAGE30_11_8_CONFIRMATION_ADAPTER_MODULE",
        "STAGE30_11_8_FAKE_CONFIRMATION_PROOF_MODULE",
        "STAGE30_11_8_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE",
        "STAGE30_11_8_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_8_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_8_TEST_BASENAMES",
        "STAGE30_11_8_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_8_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_8_CONFIRMATION_DECISIONS",
        "STAGE30_11_8_CONFIRMATION_REASONS",
        "STAGE30_11_8_MIGRATION_EVIDENCE_FIELDS",
        "STAGE30_11_8_MIGRATION_RESOLUTION_FIELDS",
        "STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT",
        "STAGE30_11_8_NEXT_ALLOWED_STAGE",
        "STAGE30_11_8_FORBIDDEN_SURFACES",
        "STAGE30_11_8_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_8_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_through_30_11_7_constants_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_5_MINOR_VERSION",
        "STAGE30_11_6_MINOR_VERSION",
        "STAGE30_11_7_MINOR_VERSION",
        "STAGE30_11_7_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_7_NEXT_ALLOWED_STAGE",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 10. Stage 30.11.9+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_9_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_8_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_8_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 9:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.8 inventory must not admit a Stage 30.11.9+ file yet; "
        f"saw {violations!r}"
    )
