"""Stage 30.11.21 manifest pin tests.

Pins the Stage 30.11.21 manifest constants (minor version, report schema version,
source stage, spec-lock doc, the three production basenames + module paths, the test
basenames, the stdlib + PHX2 import allowlists, the bounded caps, the duck-typed
evidence-source + Stage 30.11.8 resolution surface pins, the closed-set Layer-0
enrichment decision + redaction vocabularies, the enriched migration fields, the
dataclass field tuples, the forbidden surfaces, the next-allowed-stage pointer, the
operator-auth note), cross-checks the mirrored values against the Stage 30.11.21
models module + the committed Stage 30.11.18 facts type + the committed Stage 30.11.8
confirmation vocabulary + the committed Stage 30.11.9 evidence-source adapter (BY
VALUE -- the committed production code reuses the Stage 30.11.8 confirmation and reads
the Stage 30.11.9 source duck-typed; only this test cross-checks the mirror), asserts
the production + test files + spec-lock doc exist, and confirms the manifest
``__all__`` exports the surface while the earlier sections survive.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_19_ENRICHED_MARKET_FIELDS,
    STAGE30_11_20_ENRICHED_PRICE_FIELDS,
    STAGE30_11_21_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_21_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_21_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_21_CONFIRM_DECISION_CONFIRMED,
    STAGE30_11_21_DEFAULT_MAX_CANDIDATES,
    STAGE30_11_21_ENRICHED_MIGRATION_FIELDS,
    STAGE30_11_21_ENRICHMENT_ADAPTER_BASENAME,
    STAGE30_11_21_ENRICHMENT_ADAPTER_MODULE,
    STAGE30_11_21_ENRICHMENT_DECISIONS,
    STAGE30_11_21_ENRICHMENT_EVENT_FIELDS,
    STAGE30_11_21_ENRICHMENT_MODELS_BASENAME,
    STAGE30_11_21_ENRICHMENT_MODELS_MODULE,
    STAGE30_11_21_ENRICHMENT_RESULT_FIELDS,
    STAGE30_11_21_ENRICHMENT_SESSION_REPORT_FIELDS,
    STAGE30_11_21_EVIDENCE_SOURCE_METHOD,
    STAGE30_11_21_FAKE_ENRICHMENT_PROOF_BASENAME,
    STAGE30_11_21_FAKE_ENRICHMENT_PROOF_MODULE,
    STAGE30_11_21_FORBIDDEN_SURFACES,
    STAGE30_11_21_LIVE_CEREMONY_NOTE,
    STAGE30_11_21_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_21_MAX_CANDIDATES_HARD_CAP,
    STAGE30_11_21_MIGRATION_RESOLUTION_REQUIRED_ATTRS,
    STAGE30_11_21_MINOR_VERSION,
    STAGE30_11_21_NEXT_ALLOWED_STAGE,
    STAGE30_11_21_REDACTION_STATUS_REDACTED,
    STAGE30_11_21_REDACTION_STATUSES,
    STAGE30_11_21_REPORT_SCHEMA_VERSION,
    STAGE30_11_21_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_21_SOURCE_STAGE,
    STAGE30_11_21_TEST_BASENAMES,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_adapter import (
    resolve_candidate_migration,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    CONFIRM_DECISION_CONFIRMED,
    STAGE30_11_8_FAIL_CLOSED_REASONS,
    Stage30_11_8MigrationResolution,
    migration_resolution_field_names,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_adapter import (
    Stage30_11_9MigrationEvidenceSourceAdapter,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    STAGE30_11_17_MAX_CANDIDATES_HARD_CAP,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_21_migration_time_enrichment_models import (
    STAGE30_11_21_CONFIRM_DECISION_CONFIRMED as MODELS_CONFIRM,
    STAGE30_11_21_ENRICHMENT_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_21_EVIDENCE_SOURCE_METHOD as MODELS_EVIDENCE_METHOD,
    STAGE30_11_21_MIGRATION_RESOLUTION_REQUIRED_ATTRS as MODELS_RESOLUTION_ATTRS,
    STAGE30_11_21_MINOR_VERSION as MODELS_MINOR,
    STAGE30_11_21_REDACTION_STATUSES as MODELS_REDACTION_STATUSES,
    STAGE30_11_21_REDACTION_STATUS_REDACTED as MODELS_REDACTED,
    STAGE30_11_21_REPORT_SCHEMA_VERSION as MODELS_SCHEMA,
    STAGE30_11_21_SOURCE_STAGE as MODELS_SOURCE_STAGE,
    migration_enrichment_event_field_names,
    migration_enrichment_result_field_names,
    migration_enrichment_session_report_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
DOCS_ROOT: Path = PHX2_ROOT / "docs"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_21_MINOR_VERSION == "30.11.21"
    assert STAGE30_11_21_MINOR_VERSION == MODELS_MINOR


def test_schema_version_and_source_stage_match_models() -> None:
    assert STAGE30_11_21_REPORT_SCHEMA_VERSION == (
        "stage30_11_21_v0_migration_time_enrichment"
    )
    assert STAGE30_11_21_REPORT_SCHEMA_VERSION == MODELS_SCHEMA
    assert STAGE30_11_21_SOURCE_STAGE == "30.11.21"
    assert STAGE30_11_21_SOURCE_STAGE == MODELS_SOURCE_STAGE


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory + files exist
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_21_ENRICHMENT_MODELS_BASENAME == (
        "stage30_11_21_migration_time_enrichment_models.py"
    )
    assert STAGE30_11_21_ENRICHMENT_ADAPTER_BASENAME == (
        "stage30_11_21_migration_time_enrichment_adapter.py"
    )
    assert STAGE30_11_21_FAKE_ENRICHMENT_PROOF_BASENAME == (
        "stage30_11_21_fake_migration_time_enrichment_proof.py"
    )
    assert STAGE30_11_21_ENRICHMENT_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_21_migration_time_enrichment_models"
    )
    assert STAGE30_11_21_ENRICHMENT_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_21_migration_time_enrichment_adapter"
    )
    assert STAGE30_11_21_FAKE_ENRICHMENT_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_21_fake_migration_time_enrichment_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_21_ENRICHMENT_MODELS_BASENAME,
        STAGE30_11_21_ENRICHMENT_ADAPTER_BASENAME,
        STAGE30_11_21_FAKE_ENRICHMENT_PROOF_BASENAME,
    )
    assert STAGE30_11_21_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_21_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_21_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.21 requires {basename}"
        )


def test_spec_lock_doc_exists() -> None:
    assert (
        DOCS_ROOT
        / "STAGE_30_11_21_MIGRATION_TIME_ENRICHMENT_SPEC_LOCK.md"
    ).is_file()


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_21_TEST_BASENAMES == (
        "test_stage_30_11_21_migration_time_enrichment_adapter.py",
        "test_stage_30_11_21_fake_migration_time_enrichment_proof.py",
        "test_stage_30_11_21_boundaries.py",
        "test_stage_30_11_21_manifest.py",
    )
    for basename in STAGE30_11_21_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.21 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists (stdlib + PHX2)
# ---------------------------------------------------------------------------


def test_stdlib_allowlist_pinned() -> None:
    assert STAGE30_11_21_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    # The confirmation + anchor validation REUSE the committed Stage 30.11.8
    # authority, so no decimal / re / io / db / clock is admitted.
    for forbidden in ("os", "json", "pathlib", "datetime", "decimal", "re", "sqlite3"):
        assert forbidden not in STAGE30_11_21_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_within_family_no_stage27_28_29_or_birdeye() -> None:
    assert STAGE30_11_21_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_21_ENRICHMENT_MODELS_MODULE,
        STAGE30_11_21_ENRICHMENT_ADAPTER_MODULE,
        STAGE30_11_21_FAKE_ENRICHMENT_PROOF_MODULE,
        "PHX2.stage30.stage30_11_20_current_price_enrichment_adapter",
        "PHX2.stage30.stage30_11_8_migration_confirmation_adapter",
        "PHX2.stage30.stage30_11_8_migration_confirmation_models",
        "PHX2.stage30.stage30_11_18_harvested_facts_models",
        "PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models",
        "PHX2.stage30.stage30_11_15_ping_dedupe_ledger",
        "PHX2.stage30.stage30_11_5_fake_live_wiring_proof",
    )
    for module in STAGE30_11_21_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_21_ALLOWED_PHX2_IMPORTS)
    assert "stage27" not in joined
    assert "stage28" not in joined
    assert "stage29" not in joined
    assert "stage30_4_3" not in joined
    assert "birdeye" not in joined
    assert "stage30_11_11" not in joined
    assert "stage30_11_16" not in joined


# ---------------------------------------------------------------------------
# 4. Bounded caps + duck-typed evidence-source / resolution surface pins
# ---------------------------------------------------------------------------


def test_caps_pinned_and_mirror_committed_session() -> None:
    assert STAGE30_11_21_MAX_CANDIDATES_HARD_CAP == 10
    assert STAGE30_11_21_MAX_CANDIDATES_HARD_CAP == (
        STAGE30_11_17_MAX_CANDIDATES_HARD_CAP
    )
    assert STAGE30_11_21_DEFAULT_MAX_CANDIDATES == 10


def test_evidence_source_method_pinned_and_exists_on_committed_30_11_9() -> None:
    # The locked key decision: the committed Stage 30.11.8 confirmation calls
    # ``lookup_migration_evidence`` on the injected evidence source -- the surface
    # the committed Stage 30.11.9 mint-keyed adapter natively exposes.
    assert STAGE30_11_21_EVIDENCE_SOURCE_METHOD == "lookup_migration_evidence"
    assert STAGE30_11_21_EVIDENCE_SOURCE_METHOD == MODELS_EVIDENCE_METHOD
    assert callable(
        getattr(
            Stage30_11_9MigrationEvidenceSourceAdapter,
            STAGE30_11_21_EVIDENCE_SOURCE_METHOD,
            None,
        )
    ), (
        "the committed Stage 30.11.9 evidence-source adapter must natively expose "
        "the duck-typed surface the Stage 30.11.8 confirmation Stage 30.11.21 reuses "
        "calls"
    )


def test_resolution_attrs_pinned_and_subset_of_committed_resolution() -> None:
    assert STAGE30_11_21_MIGRATION_RESOLUTION_REQUIRED_ATTRS == (
        "confirmed",
        "migration_event_time_utc",
        "source_ref",
        "reason",
    )
    assert STAGE30_11_21_MIGRATION_RESOLUTION_REQUIRED_ATTRS == (
        MODELS_RESOLUTION_ATTRS
    )
    # Every attr the enrichment reads must exist on the committed Stage 30.11.8
    # resolution -- this pin breaks loudly if Stage 30.11.8 renames a field.
    resolution_fields = set(migration_resolution_field_names())
    assert set(STAGE30_11_21_MIGRATION_RESOLUTION_REQUIRED_ATTRS) <= (
        resolution_fields
    )


def test_confirm_decision_pin_mirrors_committed_30_11_8_by_value() -> None:
    # The committed production code reuses the Stage 30.11.8 confirmation; the pin
    # breaks loudly if Stage 30.11.8 ever renames its confirm decision.
    assert STAGE30_11_21_CONFIRM_DECISION_CONFIRMED == "CONFIRMED_MIGRATION"
    assert STAGE30_11_21_CONFIRM_DECISION_CONFIRMED == CONFIRM_DECISION_CONFIRMED
    assert STAGE30_11_21_CONFIRM_DECISION_CONFIRMED == MODELS_CONFIRM


# ---------------------------------------------------------------------------
# 5. Closed-set vocabularies (mirrored) + the Stage 30.11.8 fail-reason mirror
# ---------------------------------------------------------------------------


def test_enrichment_decisions_pinned_and_match_models() -> None:
    assert STAGE30_11_21_ENRICHMENT_DECISIONS[0] == "ENRICHED"
    assert len(STAGE30_11_21_ENRICHMENT_DECISIONS) == 13
    assert STAGE30_11_21_ENRICHMENT_DECISIONS == MODELS_DECISIONS
    for decision in STAGE30_11_21_ENRICHMENT_DECISIONS[1:]:
        assert decision.startswith("SKIPPED_")
    assert (
        STAGE30_11_21_ENRICHMENT_DECISIONS[1] == "SKIPPED_NOT_BASE_FACTS"
    )


def test_skipped_tokens_mirror_the_committed_30_11_8_fail_reasons() -> None:
    # The ten evidence / anchor SKIPPED tokens carry the committed Stage 30.11.8
    # fail reason VERBATIM after the SKIPPED_ prefix; the mirror is exact (no extra,
    # no missing), so the session report shows the precise confirmation cause.
    evidence_skips = set(STAGE30_11_21_ENRICHMENT_DECISIONS) - {
        "ENRICHED",
        "SKIPPED_NOT_BASE_FACTS",
    }
    expected = {"SKIPPED_" + reason for reason in STAGE30_11_8_FAIL_CLOSED_REASONS}
    assert evidence_skips == expected
    # The committed Stage 30.11.8 ships exactly eleven fail-closed reasons.
    assert len(STAGE30_11_8_FAIL_CLOSED_REASONS) == 11
    assert len(evidence_skips) == 11


def test_redaction_statuses_pinned_and_match_models() -> None:
    assert STAGE30_11_21_REDACTION_STATUS_REDACTED == "REDACTED"
    assert STAGE30_11_21_REDACTION_STATUS_REDACTED == MODELS_REDACTED
    assert STAGE30_11_21_REDACTION_STATUSES == ("REDACTED", "REDACTION_VIOLATION")
    assert STAGE30_11_21_REDACTION_STATUSES == MODELS_REDACTION_STATUSES


# ---------------------------------------------------------------------------
# 6. Enriched migration fields + dataclass field tuples (mirrored)
# ---------------------------------------------------------------------------


def test_enriched_migration_fields_are_the_three_migration_fields() -> None:
    facts_field_names = {
        f.name for f in dataclass_fields(Stage30_11_18HarvestedCandidateFacts)
    }
    assert set(STAGE30_11_21_ENRICHED_MIGRATION_FIELDS) <= facts_field_names
    assert STAGE30_11_21_ENRICHED_MIGRATION_FIELDS == (
        "migration_time_utc",
        "migration_confirmed",
        "migration_source",
    )
    # The three seams are disjoint: the migration fields touch neither the Stage
    # 30.11.20 price field nor the Stage 30.11.19 market-context bundle.
    migration = set(STAGE30_11_21_ENRICHED_MIGRATION_FIELDS)
    assert migration & set(STAGE30_11_20_ENRICHED_PRICE_FIELDS) == set()
    assert migration & set(STAGE30_11_19_ENRICHED_MARKET_FIELDS) == set()
    # age_display is NEVER enriched here (no clock derivation).
    assert "age_display" not in STAGE30_11_21_ENRICHED_MIGRATION_FIELDS


def test_field_tuples_pinned_and_match_models() -> None:
    assert STAGE30_11_21_ENRICHMENT_RESULT_FIELDS == (
        migration_enrichment_result_field_names()
    )
    assert STAGE30_11_21_ENRICHMENT_EVENT_FIELDS == (
        migration_enrichment_event_field_names()
    )
    assert STAGE30_11_21_ENRICHMENT_SESSION_REPORT_FIELDS == (
        migration_enrichment_session_report_field_names()
    )


def test_event_and_report_fields_carry_no_anchor_url_or_secret() -> None:
    for name in (
        STAGE30_11_21_ENRICHMENT_EVENT_FIELDS
        + STAGE30_11_21_ENRICHMENT_SESSION_REPORT_FIELDS
    ):
        lower = name.lower()
        for forbidden in (
            "url",
            "secret",
            "webhook",
            "body",
            "anchor",
            "source_ref",
        ):
            assert forbidden not in lower, (
                f"Stage 30.11.21 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces + next allowed stage + operator-auth note
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_21_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_21_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_21_FORBIDDEN_SURFACES)
    for token in (
        "new migration fetcher",
        "bare migration timestamp copy",
        "fake migration confirmation",
        "Stage 30.11.8 confirmation edit",
        "Stage 30.11.11 migration-anchored ATH import",
        "Stage 27 direct import",
        "Stage 29 direct import",
        "real send",
        "Discord send",
        "env read",
        "live run",
        "age_display clock derivation",
        "Stage 30.11.16 real-send guard call",
        "silent pass-through on skip",
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
            f"Stage 30.11.21 forbidden surfaces must name {token!r}"
        )


def test_next_allowed_stage_is_the_separate_ceremony_steps() -> None:
    assert STAGE30_11_21_NEXT_ALLOWED_STAGE == (
        "operator-authorized real-fed dry-run ceremony + capped private send "
        "(separate steps)"
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_21_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True
    assert isinstance(STAGE30_11_21_LIVE_CEREMONY_NOTE, str)
    assert STAGE30_11_21_LIVE_CEREMONY_NOTE != ""


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the surface + earlier sections survive
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_21_surface() -> None:
    for name in (
        "STAGE30_11_21_MINOR_VERSION",
        "STAGE30_11_21_REPORT_SCHEMA_VERSION",
        "STAGE30_11_21_SOURCE_STAGE",
        "STAGE30_11_21_SPEC_LOCK_FILENAME",
        "STAGE30_11_21_SPEC_LOCK_PATH_PARTS",
        "STAGE30_11_21_ENRICHMENT_MODELS_BASENAME",
        "STAGE30_11_21_ENRICHMENT_ADAPTER_BASENAME",
        "STAGE30_11_21_FAKE_ENRICHMENT_PROOF_BASENAME",
        "STAGE30_11_21_ENRICHMENT_MODELS_MODULE",
        "STAGE30_11_21_ENRICHMENT_ADAPTER_MODULE",
        "STAGE30_11_21_FAKE_ENRICHMENT_PROOF_MODULE",
        "STAGE30_11_21_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_21_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_21_TEST_BASENAMES",
        "STAGE30_11_21_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_21_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_21_MAX_CANDIDATES_HARD_CAP",
        "STAGE30_11_21_DEFAULT_MAX_CANDIDATES",
        "STAGE30_11_21_EVIDENCE_SOURCE_METHOD",
        "STAGE30_11_21_MIGRATION_RESOLUTION_REQUIRED_ATTRS",
        "STAGE30_11_21_CONFIRM_DECISION_CONFIRMED",
        "STAGE30_11_21_ENRICHMENT_DECISIONS",
        "STAGE30_11_21_ENRICHED_MIGRATION_FIELDS",
        "STAGE30_11_21_REDACTION_STATUS_REDACTED",
        "STAGE30_11_21_REDACTION_STATUSES",
        "STAGE30_11_21_ENRICHMENT_RESULT_FIELDS",
        "STAGE30_11_21_ENRICHMENT_EVENT_FIELDS",
        "STAGE30_11_21_ENRICHMENT_SESSION_REPORT_FIELDS",
        "STAGE30_11_21_NEXT_ALLOWED_STAGE",
        "STAGE30_11_21_FORBIDDEN_SURFACES",
        "STAGE30_11_21_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_21_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_sections_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_18_MINOR_VERSION",
        "STAGE30_11_19_MINOR_VERSION",
        "STAGE30_11_20_MINOR_VERSION",
        "STAGE30_11_20_LIVE_CEREMONY_NOTE",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__


# The committed confirmation entrypoint the adapter reuses must be importable +
# callable (a light end-to-end pin that the reused authority exists).
def test_committed_confirmation_entrypoint_is_reusable() -> None:
    assert callable(resolve_candidate_migration)
    # A bare evidence-less resolution fails closed (confirmed is not True), proving
    # the reused authority is the real fail-closed confirmation.
    resolution = resolve_candidate_migration(
        {"token_mint": "mint-x"}, evidence_source=None
    )
    assert isinstance(resolution, Stage30_11_8MigrationResolution)
    assert resolution.confirmed is False
