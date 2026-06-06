"""Stage 30.11.10 manifest pin tests.

Pins the Stage 30.11.10 manifest constants (minor version, ATH-resolver schema version,
the three production basenames + module paths, the test-composed committed Stage 30.11.7
/ 30.11.8 / 30.11.9 + Stage 27.4 modules, the inventory + scanned + test basenames, the
stdlib + PHX2 import allowlists, the mirrored Stage 27.4 vocabulary, the decision / reason
closed sets, the record + resolution + summary + run-result field names, the expected
proof counts, the operator-authorized next-step token, the slice forbidden surfaces, the
operator-auth live-ceremony note), asserts the files exist, cross-checks the mirrored
schema version + field tuples against the Stage 30.11.10 models module (and the Stage
30.11.7 ATH resolver result fields + the Stage 27.4 AthContextRecord fields), cross-checks
the expected counts against the fake proof, confirms the Stage 30.11.0..30.11.9
next-allowed pointers + family pointer survive unchanged, and pins the Stage 30.11.11+ /
Stage 31 future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_8_NEXT_ALLOWED_STAGE,
    STAGE30_11_9_NEXT_ALLOWED_STAGE,
    STAGE30_11_10_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_10_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_10_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_10_ATH_CONTEXT_RECORD_FIELDS,
    STAGE30_11_10_ATH_DECISIONS,
    STAGE30_11_10_ATH_PASS_DECISION,
    STAGE30_11_10_ATH_PASS_REASON,
    STAGE30_11_10_ATH_REASONS,
    STAGE30_11_10_ATH_RESOLUTION_FIELDS,
    STAGE30_11_10_ATH_RESOLVER_ADAPTER_BASENAME,
    STAGE30_11_10_ATH_RESOLVER_ADAPTER_MODULE,
    STAGE30_11_10_ATH_RESOLVER_MODELS_BASENAME,
    STAGE30_11_10_ATH_RESOLVER_MODELS_MODULE,
    STAGE30_11_10_ATH_RESOLVER_RUN_RESULT_FIELDS,
    STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION,
    STAGE30_11_10_ATH_RESOLVER_SUMMARY_FIELDS,
    STAGE30_11_10_ATH_STATUS_PRESENT,
    STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE30_11_10_EXPECTED_BASES_SEEN,
    STAGE30_11_10_EXPECTED_RESOLVED,
    STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT,
    STAGE30_11_10_EXPECTED_UNRESOLVED,
    STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_BASENAME,
    STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_MODULE,
    STAGE30_11_10_FORBIDDEN_SURFACES,
    STAGE30_11_10_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_10_MINOR_VERSION,
    STAGE30_11_10_NEXT_ALLOWED_STAGE,
    STAGE30_11_10_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_10_TEST_BASENAMES,
    STAGE30_11_10_TEST_COMPOSES_STAGE27_4_ATH_READER_MODULE,
    STAGE30_11_10_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE,
    STAGE30_11_10_TEST_COMPOSES_STAGE30_11_8_CONFIRMATION_ADAPTER_MODULE,
    STAGE30_11_10_TEST_COMPOSES_STAGE30_11_9_EVIDENCE_SOURCE_ADAPTER_MODULE,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    ath_resolution_field_names as stage_30_11_7_ath_resolution_field_names,
)
from PHX2.stage30.stage30_11_10_ath_resolver_models import (
    STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_10_MINOR_VERSION as MODELS_MINOR_VERSION,
    ath_context_record_field_names,
    ath_resolution_field_names,
    ath_resolver_run_result_field_names,
    ath_resolver_summary_field_names,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_STATUS_PRESENT as STAGE27_4_ATH_STATUS_PRESENT,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH as STAGE27_4_DD_BASIS,
    AthContextRecord as Stage27_4AthContextRecord,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor + schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_10_MINOR_VERSION == "30.11.10"
    assert STAGE30_11_10_MINOR_VERSION == MODELS_MINOR_VERSION


def test_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION == (
        "stage30_11_10_v0_ath_resolver"
    )
    assert STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_10_ATH_RESOLVER_MODELS_BASENAME,
        STAGE30_11_10_ATH_RESOLVER_ADAPTER_BASENAME,
        STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_BASENAME,
    )
    assert STAGE30_11_10_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_10_SCANNED_PRODUCTION_BASENAMES == expected


def test_basenames_and_module_paths_pinned() -> None:
    assert STAGE30_11_10_ATH_RESOLVER_MODELS_BASENAME == (
        "stage30_11_10_ath_resolver_models.py"
    )
    assert STAGE30_11_10_ATH_RESOLVER_ADAPTER_BASENAME == (
        "stage30_11_10_ath_resolver_adapter.py"
    )
    assert STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_BASENAME == (
        "stage30_11_10_fake_ath_resolver_proof.py"
    )
    assert STAGE30_11_10_ATH_RESOLVER_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_10_ath_resolver_models"
    )
    assert STAGE30_11_10_ATH_RESOLVER_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_10_ath_resolver_adapter"
    )
    assert STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_10_fake_ath_resolver_proof"
    )
    # The committed modules the TEST composes (NOT production).
    assert STAGE30_11_10_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_7_candidate_enrichment_adapter"
    )
    assert STAGE30_11_10_TEST_COMPOSES_STAGE30_11_8_CONFIRMATION_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_8_migration_confirmation_adapter"
    )
    assert STAGE30_11_10_TEST_COMPOSES_STAGE30_11_9_EVIDENCE_SOURCE_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_9_migration_evidence_source_adapter"
    )
    assert STAGE30_11_10_TEST_COMPOSES_STAGE27_4_ATH_READER_MODULE == (
        "PHX2.stage27.price_ath_context_reader"
    )


def test_production_and_test_files_exist() -> None:
    for basename in STAGE30_11_10_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file()
    assert STAGE30_11_10_TEST_BASENAMES == (
        "test_stage_30_11_10_ath_resolver_models.py",
        "test_stage_30_11_10_ath_resolver_adapter.py",
        "test_stage_30_11_10_fake_ath_resolver_proof.py",
        "test_stage_30_11_10_composition.py",
        "test_stage_30_11_10_boundaries.py",
        "test_stage_30_11_10_manifest.py",
    )
    for basename in STAGE30_11_10_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file()


# ---------------------------------------------------------------------------
# 3. Import allowlists (the slice is a LEAF; no broad prefix; no decimal / re)
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_10_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    for forbidden in (
        "decimal",
        "re",
        "os",
        "json",
        "pathlib",
        "sqlite3",
        "time",
        "datetime",
    ):
        assert forbidden not in STAGE30_11_10_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_exactly_the_three_own_siblings() -> None:
    assert STAGE30_11_10_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_10_ATH_RESOLVER_MODELS_MODULE,
        STAGE30_11_10_ATH_RESOLVER_ADAPTER_MODULE,
        STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_MODULE,
    )
    assert len(STAGE30_11_10_ALLOWED_PHX2_IMPORTS) == 3
    for module in STAGE30_11_10_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_11_10_")
    for prefix in ("PHX2.stage30", "PHX2.stage30.stage30_11_10_"):
        assert prefix not in STAGE30_11_10_ALLOWED_PHX2_IMPORTS


# ---------------------------------------------------------------------------
# 4. Field tuples (mirrored from models; resolution >= 30.11.7; record <= 27.4)
# ---------------------------------------------------------------------------


def test_field_tuples_match_models() -> None:
    assert STAGE30_11_10_ATH_CONTEXT_RECORD_FIELDS == (
        ath_context_record_field_names()
    )
    assert STAGE30_11_10_ATH_RESOLUTION_FIELDS == ath_resolution_field_names()
    assert STAGE30_11_10_ATH_RESOLVER_SUMMARY_FIELDS == (
        ath_resolver_summary_field_names()
    )
    assert STAGE30_11_10_ATH_RESOLVER_RUN_RESULT_FIELDS == (
        ath_resolver_run_result_field_names()
    )


def test_resolution_fields_superset_of_stage_30_11_7_ath_result() -> None:
    assert set(stage_30_11_7_ath_resolution_field_names()) <= set(
        STAGE30_11_10_ATH_RESOLUTION_FIELDS
    )


def test_record_fields_subset_of_stage_27_4_ath_record() -> None:
    assert set(STAGE30_11_10_ATH_CONTEXT_RECORD_FIELDS) <= set(
        Stage27_4AthContextRecord._fields
    )


def test_mirrored_ath_tokens_match_real_stage_27_4() -> None:
    assert STAGE30_11_10_ATH_STATUS_PRESENT == STAGE27_4_ATH_STATUS_PRESENT
    assert STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH == (
        STAGE27_4_DD_BASIS
    )


# ---------------------------------------------------------------------------
# 5. Decision / reason closed sets
# ---------------------------------------------------------------------------


def test_decisions_and_reasons_pinned() -> None:
    assert STAGE30_11_10_ATH_DECISIONS == ("RESOLVED_ATH", "UNRESOLVED_ATH")
    assert STAGE30_11_10_ATH_PASS_DECISION == "RESOLVED_ATH"
    assert STAGE30_11_10_ATH_PASS_REASON == "RESOLVED_POST_MIGRATION_ATH"
    assert STAGE30_11_10_ATH_PASS_REASON == STAGE30_11_10_ATH_REASONS[0]
    assert len(STAGE30_11_10_ATH_REASONS) == 10
    assert len(set(STAGE30_11_10_ATH_REASONS)) == 10


# ---------------------------------------------------------------------------
# 6. Expected proof counts (pinned + cross-checked vs the fake proof)
# ---------------------------------------------------------------------------


def test_expected_counts_pinned() -> None:
    assert STAGE30_11_10_EXPECTED_BASES_SEEN == 9
    assert STAGE30_11_10_EXPECTED_RESOLVED == 1
    assert STAGE30_11_10_EXPECTED_UNRESOLVED == 8
    assert STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT == "mint-resolved"


def test_expected_counts_match_the_fake_proof() -> None:
    from PHX2.stage30.stage30_11_10_fake_ath_resolver_proof import (
        run_stage30_11_10_fake_ath_resolver,
    )

    run = run_stage30_11_10_fake_ath_resolver()
    s = run.summary
    assert s.bases_seen == STAGE30_11_10_EXPECTED_BASES_SEEN
    assert s.resolved == STAGE30_11_10_EXPECTED_RESOLVED
    assert s.unresolved == STAGE30_11_10_EXPECTED_UNRESOLVED
    resolved = {
        o.token_mint for o in run.outcomes if o.decision == "RESOLVED_ATH"
    }
    assert STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT in resolved


# ---------------------------------------------------------------------------
# 7. Next allowed step + family pointer + earlier pointers unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_step_is_the_operator_authorized_ceremony() -> None:
    assert STAGE30_11_10_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert "30.11.11" not in STAGE30_11_10_NEXT_ALLOWED_STAGE
    # The earlier scoped pointers + the family pointer survive unchanged.
    assert STAGE30_11_9_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert STAGE30_11_8_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_10_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 8. Forbidden surfaces remain locked (cover the audit's "do not" scopes)
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_10_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_10_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_10_FORBIDDEN_SURFACES)
    for token in (
        "controlled live ceremony executed in this stage",
        "real ATH reader binding",
        "real transport call",
        "private send",
        "live provider call",
        "env read",
        "wall-clock read",
        "fabricate ATH",
        "fabricate drawdown",
        "recompute drawdown",
        "recompute drawdown independently",
        "use Stage 30.7 display bridge as the runtime resolver",
        "promote a STALE ATH",
        "promote a pre-migration ATH",
        "inherit another mint ATH",
        "rebuild migration",
        "loosen migration",
        "modify Stage 29.5.7",
        "loosen Stage 30.11.8 confirmation",
        "modify Stage 30.11.8",
        "modify Stage 30.11.7 enrichment",
        "modify the dip gate",
        "change the dip gate",
        "bypass Stage 30.9.3 dip gate",
        "Stage 30.7 display bridge production import",
        "commit",
        "tag",
        "push",
        "Stage 30.11.11+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.10 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 9. Manifest __all__ exports the Stage 30.11.10 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_10_surface() -> None:
    for name in (
        "STAGE30_11_10_MINOR_VERSION",
        "STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION",
        "STAGE30_11_10_SOURCE_STAGE",
        "STAGE30_11_10_ATH_RESOLVER_MODELS_MODULE",
        "STAGE30_11_10_ATH_RESOLVER_ADAPTER_MODULE",
        "STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_MODULE",
        "STAGE30_11_10_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE",
        "STAGE30_11_10_TEST_COMPOSES_STAGE27_4_ATH_READER_MODULE",
        "STAGE30_11_10_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_10_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_10_TEST_BASENAMES",
        "STAGE30_11_10_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_10_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_10_ATH_RESOLUTION_FIELDS",
        "STAGE30_11_10_ATH_CONTEXT_RECORD_FIELDS",
        "STAGE30_11_10_ATH_REASONS",
        "STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT",
        "STAGE30_11_10_NEXT_ALLOWED_STAGE",
        "STAGE30_11_10_FORBIDDEN_SURFACES",
        "STAGE30_11_10_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_10_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_through_30_11_9_constants_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_7_NEXT_ALLOWED_STAGE",
        "STAGE30_11_8_MINOR_VERSION",
        "STAGE30_11_9_MINOR_VERSION",
        "STAGE30_11_9_NEXT_ALLOWED_STAGE",
        "STAGE30_11_9_FORBIDDEN_SURFACES",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 10. Stage 30.11.11+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_11_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_10_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_10_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 11:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.10 inventory must not admit a Stage 30.11.11+ file yet; "
        f"saw {violations!r}"
    )
