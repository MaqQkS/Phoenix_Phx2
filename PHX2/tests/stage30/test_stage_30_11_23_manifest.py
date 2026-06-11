"""Stage 30.11.23 manifest pin tests.

Pins the Stage 30.11.23 manifest constants (minor version, report schema version,
source stage, spec-lock doc, the three production basenames + module paths, the test
basenames, the stdlib + PHX2 import allowlists, the bounded summary-scan cap, the
COMPLETE / SAFE routing-hygiene tokens, the closed-set bridge decisions + pass
decision, the inert placeholders, the redaction vocabulary, the dataclass field
tuples, the forbidden surfaces, the next-allowed-stage pointer, the operator-auth
note), cross-checks the mirrored values against the Stage 30.11.23 models module + the
committed Stage 30.11.6 harvest cap + the committed Stage 30.11.17 session cap (BY
VALUE), asserts the production + test files + spec-lock doc exist, and confirms the
manifest ``__all__`` exports the surface while the earlier sections survive.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_23_ADAPTER_BASENAME,
    STAGE30_11_23_ADAPTER_MODULE,
    STAGE30_11_23_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_23_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_23_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_23_ASSEMBLED_CANDIDATE_FIELDS,
    STAGE30_11_23_BRIDGE_DECISIONS,
    STAGE30_11_23_BRIDGE_EVENT_FIELDS,
    STAGE30_11_23_BRIDGE_PASS_DECISION,
    STAGE30_11_23_BRIDGE_REPORT_FIELDS,
    STAGE30_11_23_DISCOVERED_CANDIDATE_FIELDS,
    STAGE30_11_23_EXPECTED_MEASUREMENT_STATUS,
    STAGE30_11_23_EXPECTED_REDACTION_STATUS,
    STAGE30_11_23_FAKE_PROOF_BASENAME,
    STAGE30_11_23_FAKE_PROOF_MODULE,
    STAGE30_11_23_FORBIDDEN_SURFACES,
    STAGE30_11_23_LIVE_CEREMONY_NOTE,
    STAGE30_11_23_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_23_MAX_SUMMARIES_HARD_CAP,
    STAGE30_11_23_MINOR_VERSION,
    STAGE30_11_23_MODELS_BASENAME,
    STAGE30_11_23_MODELS_MODULE,
    STAGE30_11_23_NEXT_ALLOWED_STAGE,
    STAGE30_11_23_PLACEHOLDER_DECIMAL,
    STAGE30_11_23_PLACEHOLDER_STATUS,
    STAGE30_11_23_REAL_FED_INPUTS_FIELDS,
    STAGE30_11_23_REDACTION_STATUS_REDACTED,
    STAGE30_11_23_REDACTION_STATUSES,
    STAGE30_11_23_REPORT_SCHEMA_VERSION,
    STAGE30_11_23_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_23_SOURCE_STAGE,
    STAGE30_11_23_SPEC_LOCK_FILENAME,
    STAGE30_11_23_TEST_BASENAMES,
)
from PHX2.stage30.stage30_11_6_candidate_source_models import (
    STAGE30_11_6_MAX_HARVEST_HARD_CAP,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    STAGE30_11_17_MAX_CANDIDATES_HARD_CAP,
)
from PHX2.stage30.stage30_11_23_migration_evidence_candidate_bridge_models import (
    STAGE30_11_23_BRIDGE_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_23_BRIDGE_PASS_DECISION as MODELS_PASS,
    STAGE30_11_23_EXPECTED_MEASUREMENT_STATUS as MODELS_MEAS,
    STAGE30_11_23_EXPECTED_REDACTION_STATUS as MODELS_REDAC,
    STAGE30_11_23_MAX_SUMMARIES_HARD_CAP as MODELS_CAP,
    STAGE30_11_23_PLACEHOLDER_DECIMAL as MODELS_PLACEHOLDER_DECIMAL,
    STAGE30_11_23_PLACEHOLDER_STATUS as MODELS_PLACEHOLDER_STATUS,
    STAGE30_11_23_REDACTION_STATUSES as MODELS_REDACTION_STATUSES,
    STAGE30_11_23_REDACTION_STATUS_REDACTED as MODELS_REDACTED,
    STAGE30_11_23_REPORT_SCHEMA_VERSION as MODELS_SCHEMA,
    STAGE30_11_23_SOURCE_STAGE as MODELS_SOURCE_STAGE,
    assembled_candidate_field_names,
    bridge_event_field_names,
    bridge_report_field_names,
    discovered_candidate_field_names,
    real_fed_inputs_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
DOCS_ROOT: Path = PHX2_ROOT / "docs"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_11_23_MINOR_VERSION == "30.11.23"


def test_schema_version_and_source_stage_match_models() -> None:
    assert STAGE30_11_23_REPORT_SCHEMA_VERSION == (
        "stage30_11_23_v0_migration_evidence_candidate_bridge"
    )
    assert STAGE30_11_23_REPORT_SCHEMA_VERSION == MODELS_SCHEMA
    assert STAGE30_11_23_SOURCE_STAGE == "30.11.23"
    assert STAGE30_11_23_SOURCE_STAGE == MODELS_SOURCE_STAGE


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory + files exist
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_23_MODELS_BASENAME == (
        "stage30_11_23_migration_evidence_candidate_bridge_models.py"
    )
    assert STAGE30_11_23_ADAPTER_BASENAME == (
        "stage30_11_23_migration_evidence_candidate_bridge_adapter.py"
    )
    assert STAGE30_11_23_FAKE_PROOF_BASENAME == (
        "stage30_11_23_fake_migration_evidence_candidate_bridge_proof.py"
    )
    assert STAGE30_11_23_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_23_migration_evidence_candidate_bridge_models"
    )
    assert STAGE30_11_23_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_23_migration_evidence_candidate_bridge_adapter"
    )
    assert STAGE30_11_23_FAKE_PROOF_MODULE == (
        "PHX2.stage30."
        "stage30_11_23_fake_migration_evidence_candidate_bridge_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_23_MODELS_BASENAME,
        STAGE30_11_23_ADAPTER_BASENAME,
        STAGE30_11_23_FAKE_PROOF_BASENAME,
    )
    assert STAGE30_11_23_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_23_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_23_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.23 requires {basename}"
        )


def test_spec_lock_doc_exists() -> None:
    assert STAGE30_11_23_SPEC_LOCK_FILENAME == (
        "STAGE_30_11_23_MIGRATION_EVIDENCE_CANDIDATE_BRIDGE_SPEC_LOCK.md"
    )
    assert (DOCS_ROOT / STAGE30_11_23_SPEC_LOCK_FILENAME).is_file()


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_23_TEST_BASENAMES == (
        "test_stage_30_11_23_migration_evidence_candidate_bridge_adapter.py",
        "test_stage_30_11_23_fake_migration_evidence_candidate_bridge_proof.py",
        "test_stage_30_11_23_boundaries.py",
        "test_stage_30_11_23_manifest.py",
    )
    for basename in STAGE30_11_23_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.23 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists (stdlib + PHX2)
# ---------------------------------------------------------------------------


def test_stdlib_allowlist_pinned() -> None:
    assert STAGE30_11_23_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    for forbidden in (
        "os",
        "json",
        "pathlib",
        "datetime",
        "decimal",
        "re",
        "sqlite3",
    ):
        assert forbidden not in STAGE30_11_23_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_reuses_30_11_9_and_30_11_22_no_stage21_29() -> None:
    assert STAGE30_11_23_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_23_MODELS_MODULE,
        STAGE30_11_23_ADAPTER_MODULE,
        STAGE30_11_23_FAKE_PROOF_MODULE,
        "PHX2.stage30.stage30_11_9_migration_evidence_source_adapter",
        "PHX2.stage30.stage30_11_22_fake_real_fed_dry_run_proof",
    )
    for module in STAGE30_11_23_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_23_ALLOWED_PHX2_IMPORTS)
    assert "stage27" not in joined
    assert "stage28" not in joined
    assert "stage29" not in joined
    assert "stage30_4_3" not in joined
    assert "birdeye" not in joined
    assert "stage30_11_11" not in joined
    assert "stage30_11_16" not in joined
    # It REUSES the committed Stage 30.11.9 mapper + source and delegates to the
    # committed Stage 30.11.22 fake proof.
    assert (
        "PHX2.stage30.stage30_11_9_migration_evidence_source_adapter"
        in STAGE30_11_23_ALLOWED_PHX2_IMPORTS
    )
    assert (
        "PHX2.stage30.stage30_11_22_fake_real_fed_dry_run_proof"
        in STAGE30_11_23_ALLOWED_PHX2_IMPORTS
    )


# ---------------------------------------------------------------------------
# 4. Bounded cap mirrors the committed harvest + session ceilings
# ---------------------------------------------------------------------------


def test_cap_pinned_and_mirrors_committed_ceilings() -> None:
    assert STAGE30_11_23_MAX_SUMMARIES_HARD_CAP == 10
    assert STAGE30_11_23_MAX_SUMMARIES_HARD_CAP == MODELS_CAP
    assert STAGE30_11_23_MAX_SUMMARIES_HARD_CAP == STAGE30_11_6_MAX_HARVEST_HARD_CAP
    assert STAGE30_11_23_MAX_SUMMARIES_HARD_CAP == (
        STAGE30_11_17_MAX_CANDIDATES_HARD_CAP
    )


# ---------------------------------------------------------------------------
# 5. COMPLETE / SAFE routing-hygiene tokens + decisions + placeholders (mirrored)
# ---------------------------------------------------------------------------


def test_routing_hygiene_tokens_match_models() -> None:
    assert STAGE30_11_23_EXPECTED_MEASUREMENT_STATUS == "COMPLETE"
    assert STAGE30_11_23_EXPECTED_MEASUREMENT_STATUS == MODELS_MEAS
    assert STAGE30_11_23_EXPECTED_REDACTION_STATUS == "SAFE"
    assert STAGE30_11_23_EXPECTED_REDACTION_STATUS == MODELS_REDAC


def test_bridge_decisions_pinned_and_match_models() -> None:
    assert STAGE30_11_23_BRIDGE_DECISIONS == (
        "BRIDGED_CANDIDATE_AND_EVIDENCE",
        "SKIPPED_NOT_A_SUMMARY",
        "SKIPPED_MISSING_TOKEN_MINT",
        "SKIPPED_INVALID_TOKEN_MINT",
        "SKIPPED_MISSING_MIGRATION_TIME",
        "SKIPPED_NOT_COMPLETE_MEASUREMENT",
        "SKIPPED_UNSAFE_REDACTION",
        "SKIPPED_MALFORMED_WARNINGS",
        "SKIPPED_EVIDENCE_UNBUILDABLE",
        "SKIPPED_DUPLICATE_MINT",
    )
    assert STAGE30_11_23_BRIDGE_DECISIONS == MODELS_DECISIONS
    assert len(STAGE30_11_23_BRIDGE_DECISIONS) == 10
    assert len(set(STAGE30_11_23_BRIDGE_DECISIONS)) == 10
    assert STAGE30_11_23_BRIDGE_PASS_DECISION == "BRIDGED_CANDIDATE_AND_EVIDENCE"
    assert STAGE30_11_23_BRIDGE_PASS_DECISION == MODELS_PASS
    assert STAGE30_11_23_BRIDGE_PASS_DECISION in STAGE30_11_23_BRIDGE_DECISIONS


def test_placeholders_pinned_and_match_models() -> None:
    assert STAGE30_11_23_PLACEHOLDER_STATUS == "PENDING"
    assert STAGE30_11_23_PLACEHOLDER_STATUS == MODELS_PLACEHOLDER_STATUS
    assert STAGE30_11_23_PLACEHOLDER_DECIMAL == "0"
    assert STAGE30_11_23_PLACEHOLDER_DECIMAL == MODELS_PLACEHOLDER_DECIMAL
    # The status placeholder must NOT be the dispatch-eligible PRESENT value.
    assert STAGE30_11_23_PLACEHOLDER_STATUS != "PRESENT"


def test_redaction_statuses_pinned_and_match_models() -> None:
    assert STAGE30_11_23_REDACTION_STATUS_REDACTED == "REDACTED"
    assert STAGE30_11_23_REDACTION_STATUS_REDACTED == MODELS_REDACTED
    assert STAGE30_11_23_REDACTION_STATUSES == ("REDACTED", "REDACTION_VIOLATION")
    assert STAGE30_11_23_REDACTION_STATUSES == MODELS_REDACTION_STATUSES


# ---------------------------------------------------------------------------
# 6. Dataclass field tuples (mirrored)
# ---------------------------------------------------------------------------


def test_field_tuples_pinned_and_match_models() -> None:
    assert STAGE30_11_23_DISCOVERED_CANDIDATE_FIELDS == (
        discovered_candidate_field_names()
    )
    assert STAGE30_11_23_ASSEMBLED_CANDIDATE_FIELDS == (
        assembled_candidate_field_names()
    )
    assert STAGE30_11_23_BRIDGE_EVENT_FIELDS == bridge_event_field_names()
    assert STAGE30_11_23_BRIDGE_REPORT_FIELDS == bridge_report_field_names()
    assert STAGE30_11_23_REAL_FED_INPUTS_FIELDS == real_fed_inputs_field_names()


def test_bridge_event_carries_no_candidate_id_source_ref_or_magnitude() -> None:
    # The redaction-safe bridge event carries ONLY the index + decision + safe-echo
    # token mint + timestamp; no candidate_id (not known at bridge time), no
    # source_ref, no anchor, no magnitude.
    assert STAGE30_11_23_BRIDGE_EVENT_FIELDS == (
        "index",
        "decision",
        "token_mint",
        "created_at_utc",
    )
    for forbidden in (
        "candidate_id",
        "source_ref",
        "migration_event_time_utc",
        "warnings",
        "measurement_status",
        "redaction_status",
    ):
        assert forbidden not in STAGE30_11_23_BRIDGE_EVENT_FIELDS


def test_real_fed_inputs_surface_the_four_30_11_22_slots() -> None:
    for required in ("events", "assembler", "record_flattener", "evidence_source"):
        assert required in STAGE30_11_23_REAL_FED_INPUTS_FIELDS, (
            f"Stage 30.11.23 inputs must surface the {required!r} slot the "
            f"committed Stage 30.11.22 wrapper takes injected"
        )


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces + next allowed stage + operator-auth note
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_23_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_23_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_23_FORBIDDEN_SURFACES)
    for token in (
        "candidate / evidence mint desync",
        "manual curated mint feed",
        "candidate source_ref echo",
        "Stage 30.11.8 confirmation replacement",
        "Stage 30.11.22 wrapper edit",
        "Stage 29 direct import",
        "Stage 29.5.7 summary type import",
        "real provider transport construction",
        "real send",
        "Discord send",
        "webhook call",
        "env read",
        "live run",
        "Stage 30.11.16 real-send guard call",
        "Stage 30.11.16 real-send guard import",
        "durable one-send ledger mutation",
        "public routing",
        "subscriber routing",
        "wallet / signing",
        "automated trading",
        "commit",
        "tag",
        "push",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.23 forbidden surfaces must name {token!r}"
        )


def test_next_allowed_stage_is_the_separate_ceremony_steps() -> None:
    assert STAGE30_11_23_NEXT_ALLOWED_STAGE == (
        "operator-authorized real-fed dry-run ceremony + capped private send "
        "(separate steps)"
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_23_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True
    assert isinstance(STAGE30_11_23_LIVE_CEREMONY_NOTE, str)
    assert STAGE30_11_23_LIVE_CEREMONY_NOTE != ""


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the surface + earlier sections survive
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_23_surface() -> None:
    for name in (
        "STAGE30_11_23_MINOR_VERSION",
        "STAGE30_11_23_REPORT_SCHEMA_VERSION",
        "STAGE30_11_23_SOURCE_STAGE",
        "STAGE30_11_23_SPEC_LOCK_FILENAME",
        "STAGE30_11_23_SPEC_LOCK_PATH_PARTS",
        "STAGE30_11_23_MODELS_BASENAME",
        "STAGE30_11_23_ADAPTER_BASENAME",
        "STAGE30_11_23_FAKE_PROOF_BASENAME",
        "STAGE30_11_23_MODELS_MODULE",
        "STAGE30_11_23_ADAPTER_MODULE",
        "STAGE30_11_23_FAKE_PROOF_MODULE",
        "STAGE30_11_23_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_23_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_23_TEST_BASENAMES",
        "STAGE30_11_23_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_23_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_23_MAX_SUMMARIES_HARD_CAP",
        "STAGE30_11_23_EXPECTED_MEASUREMENT_STATUS",
        "STAGE30_11_23_EXPECTED_REDACTION_STATUS",
        "STAGE30_11_23_BRIDGE_DECISIONS",
        "STAGE30_11_23_BRIDGE_PASS_DECISION",
        "STAGE30_11_23_PLACEHOLDER_STATUS",
        "STAGE30_11_23_PLACEHOLDER_DECIMAL",
        "STAGE30_11_23_REDACTION_STATUS_REDACTED",
        "STAGE30_11_23_REDACTION_STATUSES",
        "STAGE30_11_23_DISCOVERED_CANDIDATE_FIELDS",
        "STAGE30_11_23_ASSEMBLED_CANDIDATE_FIELDS",
        "STAGE30_11_23_BRIDGE_EVENT_FIELDS",
        "STAGE30_11_23_BRIDGE_REPORT_FIELDS",
        "STAGE30_11_23_REAL_FED_INPUTS_FIELDS",
        "STAGE30_11_23_NEXT_ALLOWED_STAGE",
        "STAGE30_11_23_FORBIDDEN_SURFACES",
        "STAGE30_11_23_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_23_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_sections_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_21_MINOR_VERSION",
        "STAGE30_11_22_MINOR_VERSION",
        "STAGE30_11_22_NEXT_ALLOWED_STAGE",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__
