"""Stage 30.11.9 manifest pin tests.

Pins the Stage 30.11.9 manifest constants (minor version, evidence-source schema
version, the three production basenames + module paths, the test-composed committed
Stage 30.11.8 / 30.11.7 modules, the inventory + scanned + test basenames, the stdlib +
PHX2 import allowlists, the evidence-record + summary + outcome + run-result field
names, the expected proof counts, the operator-authorized next-step token, the slice
forbidden surfaces, the operator-auth live-ceremony note), asserts the files exist,
cross-checks the mirrored schema version + record fields against the Stage 30.11.9
models module (and the Stage 30.11.8 evidence shape), cross-checks the expected counts
against the fake proof, confirms the Stage 30.11.0..30.11.8 next-allowed pointers +
family pointer survive unchanged, and pins the Stage 30.11.10+ / Stage 31 future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_8_NEXT_ALLOWED_STAGE,
    STAGE30_11_9_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_9_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_9_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_9_EVIDENCE_SOURCE_PROBE_OUTCOME_FIELDS,
    STAGE30_11_9_EVIDENCE_SOURCE_RUN_RESULT_FIELDS,
    STAGE30_11_9_EVIDENCE_SOURCE_SCHEMA_VERSION,
    STAGE30_11_9_EVIDENCE_SOURCE_SUMMARY_FIELDS,
    STAGE30_11_9_EXPECTED_EVIDENCE_RETURNED,
    STAGE30_11_9_EXPECTED_NO_EVIDENCE,
    STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT,
    STAGE30_11_9_EXPECTED_PROBES_SEEN,
    STAGE30_11_9_FAKE_SOURCE_PROOF_BASENAME,
    STAGE30_11_9_FAKE_SOURCE_PROOF_MODULE,
    STAGE30_11_9_FORBIDDEN_SURFACES,
    STAGE30_11_9_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_9_MIGRATION_EVIDENCE_RECORD_FIELDS,
    STAGE30_11_9_MINOR_VERSION,
    STAGE30_11_9_NEXT_ALLOWED_STAGE,
    STAGE30_11_9_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_9_SOURCE_ADAPTER_BASENAME,
    STAGE30_11_9_SOURCE_ADAPTER_MODULE,
    STAGE30_11_9_SOURCE_MODELS_BASENAME,
    STAGE30_11_9_SOURCE_MODELS_MODULE,
    STAGE30_11_9_TEST_BASENAMES,
    STAGE30_11_9_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE,
    STAGE30_11_9_TEST_COMPOSES_STAGE30_11_8_CONFIRMATION_ADAPTER_MODULE,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    migration_evidence_field_names as STAGE30_11_8_EVIDENCE_FIELD_NAMES,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_models import (
    STAGE30_11_9_EVIDENCE_SOURCE_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_9_MINOR_VERSION as MODELS_MINOR_VERSION,
    evidence_source_probe_outcome_field_names,
    evidence_source_run_result_field_names,
    evidence_source_summary_field_names,
    migration_evidence_record_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor + schema version (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_9_MINOR_VERSION == "30.11.9"
    assert STAGE30_11_9_MINOR_VERSION == MODELS_MINOR_VERSION


def test_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_9_EVIDENCE_SOURCE_SCHEMA_VERSION == (
        "stage30_11_9_v0_migration_evidence_source"
    )
    assert STAGE30_11_9_EVIDENCE_SOURCE_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_9_SOURCE_MODELS_BASENAME,
        STAGE30_11_9_SOURCE_ADAPTER_BASENAME,
        STAGE30_11_9_FAKE_SOURCE_PROOF_BASENAME,
    )
    assert STAGE30_11_9_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_9_SCANNED_PRODUCTION_BASENAMES == expected


def test_basenames_and_module_paths_pinned() -> None:
    assert STAGE30_11_9_SOURCE_MODELS_BASENAME == (
        "stage30_11_9_migration_evidence_source_models.py"
    )
    assert STAGE30_11_9_SOURCE_ADAPTER_BASENAME == (
        "stage30_11_9_migration_evidence_source_adapter.py"
    )
    assert STAGE30_11_9_FAKE_SOURCE_PROOF_BASENAME == (
        "stage30_11_9_fake_evidence_source_proof.py"
    )
    assert STAGE30_11_9_SOURCE_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_9_migration_evidence_source_models"
    )
    assert STAGE30_11_9_SOURCE_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_9_migration_evidence_source_adapter"
    )
    assert STAGE30_11_9_FAKE_SOURCE_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_9_fake_evidence_source_proof"
    )
    # The committed modules the TEST composes (NOT production).
    assert STAGE30_11_9_TEST_COMPOSES_STAGE30_11_8_CONFIRMATION_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_8_migration_confirmation_adapter"
    )
    assert STAGE30_11_9_TEST_COMPOSES_STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_7_candidate_enrichment_adapter"
    )


def test_production_and_test_files_exist() -> None:
    for basename in STAGE30_11_9_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file()
    assert STAGE30_11_9_TEST_BASENAMES == (
        "test_stage_30_11_9_migration_evidence_source_models.py",
        "test_stage_30_11_9_migration_evidence_source_adapter.py",
        "test_stage_30_11_9_fake_evidence_source_proof.py",
        "test_stage_30_11_9_composition.py",
        "test_stage_30_11_9_boundaries.py",
        "test_stage_30_11_9_manifest.py",
    )
    for basename in STAGE30_11_9_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file()


# ---------------------------------------------------------------------------
# 3. Import allowlists (the slice is a LEAF; no broad prefix; no re)
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_9_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    for forbidden in ("re", "os", "json", "pathlib", "sqlite3", "time", "datetime"):
        assert forbidden not in STAGE30_11_9_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_exactly_the_three_own_siblings() -> None:
    assert STAGE30_11_9_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_9_SOURCE_MODELS_MODULE,
        STAGE30_11_9_SOURCE_ADAPTER_MODULE,
        STAGE30_11_9_FAKE_SOURCE_PROOF_MODULE,
    )
    assert len(STAGE30_11_9_ALLOWED_PHX2_IMPORTS) == 3
    for module in STAGE30_11_9_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_11_9_")
    for prefix in ("PHX2.stage30", "PHX2.stage30.stage30_11_9_"):
        assert prefix not in STAGE30_11_9_ALLOWED_PHX2_IMPORTS


# ---------------------------------------------------------------------------
# 4. Field tuples (mirrored from models; record fields equal the 30.11.8 evidence)
# ---------------------------------------------------------------------------


def test_record_field_tuple_matches_models_and_stage_30_11_8_evidence() -> None:
    assert STAGE30_11_9_MIGRATION_EVIDENCE_RECORD_FIELDS == (
        migration_evidence_record_field_names()
    )
    # The record mirrors the Stage 30.11.8 evidence shape BY VALUE, so the committed
    # Stage 30.11.8 confirmation reads it duck-typed.
    assert STAGE30_11_9_MIGRATION_EVIDENCE_RECORD_FIELDS == (
        STAGE30_11_8_EVIDENCE_FIELD_NAMES()
    )


def test_summary_outcome_run_result_field_tuples_match_models() -> None:
    assert STAGE30_11_9_EVIDENCE_SOURCE_SUMMARY_FIELDS == (
        evidence_source_summary_field_names()
    )
    assert STAGE30_11_9_EVIDENCE_SOURCE_PROBE_OUTCOME_FIELDS == (
        evidence_source_probe_outcome_field_names()
    )
    assert STAGE30_11_9_EVIDENCE_SOURCE_RUN_RESULT_FIELDS == (
        evidence_source_run_result_field_names()
    )


# ---------------------------------------------------------------------------
# 5. Expected proof counts (pinned + cross-checked vs the fake proof)
# ---------------------------------------------------------------------------


def test_expected_counts_pinned() -> None:
    assert STAGE30_11_9_EXPECTED_PROBES_SEEN == 7
    assert STAGE30_11_9_EXPECTED_EVIDENCE_RETURNED == 2
    assert STAGE30_11_9_EXPECTED_NO_EVIDENCE == 5
    assert STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT == "mint-present"


def test_expected_counts_match_the_fake_proof() -> None:
    from PHX2.stage30.stage30_11_9_fake_evidence_source_proof import (
        run_stage30_11_9_fake_evidence_source,
    )

    run = run_stage30_11_9_fake_evidence_source()
    s = run.summary
    assert s.probes_seen == STAGE30_11_9_EXPECTED_PROBES_SEEN
    assert s.evidence_returned == STAGE30_11_9_EXPECTED_EVIDENCE_RETURNED
    assert s.no_evidence == STAGE30_11_9_EXPECTED_NO_EVIDENCE
    present = {o.token_mint for o in run.outcomes if o.evidence_present}
    assert STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT in present


# ---------------------------------------------------------------------------
# 6. Next allowed step + family pointer + earlier 30.11.8 pointer unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_step_is_the_operator_authorized_ceremony() -> None:
    assert STAGE30_11_9_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert "30.11.10" not in STAGE30_11_9_NEXT_ALLOWED_STAGE
    # The Stage 30.11.8 scoped pointer + the family pointer survive unchanged.
    assert STAGE30_11_8_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_9_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_9_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_9_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_9_FORBIDDEN_SURFACES)
    for token in (
        "controlled live ceremony executed in this stage",
        "real provider binding",
        "real transport call",
        "private send",
        "live provider call",
        "env read",
        "wall-clock read",
        "fabricate migration evidence",
        "normalize a non-trailing-Z anchor into a passing one",
        "invent a redaction-safe claim",
        "promote an UNKNOWN reading",
        "inherit another mint migration evidence",
        "decide the migration verdict in the source",
        "loosen Stage 30.11.8 confirmation",
        "modify Stage 30.11.8 confirmation",
        "modify Stage 29.3 no-migration-evidence source",
        "bypass Stage 30.11.8 confirmation",
        "bypass Stage 30.9.3 dip gate",
        "Stage 25/27/28/29 production import",
        "Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 / Stage 30.11.8 production import",
        "commit",
        "tag",
        "push",
        "Stage 30.11.10+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.9 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the Stage 30.11.9 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_9_surface() -> None:
    for name in (
        "STAGE30_11_9_MINOR_VERSION",
        "STAGE30_11_9_EVIDENCE_SOURCE_SCHEMA_VERSION",
        "STAGE30_11_9_SOURCE_STAGE",
        "STAGE30_11_9_SOURCE_MODELS_MODULE",
        "STAGE30_11_9_SOURCE_ADAPTER_MODULE",
        "STAGE30_11_9_FAKE_SOURCE_PROOF_MODULE",
        "STAGE30_11_9_TEST_COMPOSES_STAGE30_11_8_CONFIRMATION_ADAPTER_MODULE",
        "STAGE30_11_9_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_9_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_9_TEST_BASENAMES",
        "STAGE30_11_9_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_9_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_9_MIGRATION_EVIDENCE_RECORD_FIELDS",
        "STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT",
        "STAGE30_11_9_NEXT_ALLOWED_STAGE",
        "STAGE30_11_9_FORBIDDEN_SURFACES",
        "STAGE30_11_9_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_9_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_through_30_11_8_constants_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_7_NEXT_ALLOWED_STAGE",
        "STAGE30_11_8_MINOR_VERSION",
        "STAGE30_11_8_NEXT_ALLOWED_STAGE",
        "STAGE30_11_8_FORBIDDEN_SURFACES",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 9. Stage 30.11.10+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_10_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_9_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_9_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 10:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.9 inventory must not admit a Stage 30.11.10+ file yet; "
        f"saw {violations!r}"
    )
