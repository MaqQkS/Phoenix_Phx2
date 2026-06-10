"""Stage 30.11.22 manifest pin tests.

Pins the Stage 30.11.22 manifest constants (minor version, report schema version,
source stage, spec-lock doc, the three production basenames + module paths, the test
basenames, the stdlib + PHX2 import allowlists, the bounded caps, the bridge
placeholder sentinels + verbatim / sentinel field sets, the redaction vocabulary, the
dataclass field tuples, the forbidden surfaces, the next-allowed-stage pointer, the
operator-auth note), cross-checks the mirrored values against the Stage 30.11.22
models module + the committed Stage 30.11.6 harvest cap + the committed Stage 30.11.17
session cap + the committed Stage 30.11.18 facts type (BY VALUE), asserts the
production + test files + spec-lock doc exist, and confirms the manifest ``__all__``
exports the surface while the earlier sections survive.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_22_ADAPTER_BASENAME,
    STAGE30_11_22_ADAPTER_MODULE,
    STAGE30_11_22_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_22_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_22_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_22_BRIDGE_SENTINEL_FIELDS,
    STAGE30_11_22_BRIDGE_VERBATIM_FIELDS,
    STAGE30_11_22_FAKE_PROOF_BASENAME,
    STAGE30_11_22_FAKE_PROOF_MODULE,
    STAGE30_11_22_FORBIDDEN_SURFACES,
    STAGE30_11_22_LIVE_CEREMONY_NOTE,
    STAGE30_11_22_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_22_MAX_CANDIDATES_HARD_CAP,
    STAGE30_11_22_MAX_HARVEST_HARD_CAP,
    STAGE30_11_22_MODELS_BASENAME,
    STAGE30_11_22_MODELS_MODULE,
    STAGE30_11_22_MINOR_VERSION,
    STAGE30_11_22_NEXT_ALLOWED_STAGE,
    STAGE30_11_22_NO_REAL_SEND_ATTESTATION_FIELDS,
    STAGE30_11_22_PENDING_ENRICHMENT,
    STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS,
    STAGE30_11_22_REAL_FED_DRY_RUN_REPORT_FIELDS,
    STAGE30_11_22_REDACTION_STATUS_REDACTED,
    STAGE30_11_22_REDACTION_STATUSES,
    STAGE30_11_22_REPORT_SCHEMA_VERSION,
    STAGE30_11_22_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_22_SOURCE_STAGE,
    STAGE30_11_22_TEST_BASENAMES,
)
from PHX2.stage30.stage30_11_6_candidate_source_models import (
    STAGE30_11_6_MAX_HARVEST_HARD_CAP,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    STAGE30_11_17_MAX_CANDIDATES_HARD_CAP,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_22_real_fed_dry_run_models import (
    STAGE30_11_22_PENDING_ENRICHMENT as MODELS_PENDING,
    STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS as MODELS_PENDING_MC,
    STAGE30_11_22_REDACTION_STATUSES as MODELS_REDACTION_STATUSES,
    STAGE30_11_22_REDACTION_STATUS_REDACTED as MODELS_REDACTED,
    STAGE30_11_22_REPORT_SCHEMA_VERSION as MODELS_SCHEMA,
    STAGE30_11_22_SOURCE_STAGE as MODELS_SOURCE_STAGE,
    no_real_send_attestation_field_names,
    real_fed_dry_run_report_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
DOCS_ROOT: Path = PHX2_ROOT / "docs"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_11_22_MINOR_VERSION == "30.11.22"


def test_schema_version_and_source_stage_match_models() -> None:
    assert STAGE30_11_22_REPORT_SCHEMA_VERSION == (
        "stage30_11_22_v0_real_fed_dry_run"
    )
    assert STAGE30_11_22_REPORT_SCHEMA_VERSION == MODELS_SCHEMA
    assert STAGE30_11_22_SOURCE_STAGE == "30.11.22"
    assert STAGE30_11_22_SOURCE_STAGE == MODELS_SOURCE_STAGE


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory + files exist
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_22_MODELS_BASENAME == (
        "stage30_11_22_real_fed_dry_run_models.py"
    )
    assert STAGE30_11_22_ADAPTER_BASENAME == (
        "stage30_11_22_real_fed_dry_run_adapter.py"
    )
    assert STAGE30_11_22_FAKE_PROOF_BASENAME == (
        "stage30_11_22_fake_real_fed_dry_run_proof.py"
    )
    assert STAGE30_11_22_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_22_real_fed_dry_run_models"
    )
    assert STAGE30_11_22_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_22_real_fed_dry_run_adapter"
    )
    assert STAGE30_11_22_FAKE_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_22_fake_real_fed_dry_run_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_22_MODELS_BASENAME,
        STAGE30_11_22_ADAPTER_BASENAME,
        STAGE30_11_22_FAKE_PROOF_BASENAME,
    )
    assert STAGE30_11_22_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_22_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_22_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.22 requires {basename}"
        )


def test_spec_lock_doc_exists() -> None:
    assert (
        DOCS_ROOT / "STAGE_30_11_22_REAL_FED_DRY_RUN_SPEC_LOCK.md"
    ).is_file()


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_22_TEST_BASENAMES == (
        "test_stage_30_11_22_real_fed_dry_run_adapter.py",
        "test_stage_30_11_22_fake_real_fed_dry_run_proof.py",
        "test_stage_30_11_22_boundaries.py",
        "test_stage_30_11_22_manifest.py",
    )
    for basename in STAGE30_11_22_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.22 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists (stdlib + PHX2)
# ---------------------------------------------------------------------------


def test_stdlib_allowlist_pinned() -> None:
    assert STAGE30_11_22_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    for forbidden in ("os", "json", "pathlib", "datetime", "decimal", "re", "sqlite3"):
        assert forbidden not in STAGE30_11_22_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_within_family_no_stage27_28_29_or_birdeye() -> None:
    assert STAGE30_11_22_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_22_MODELS_MODULE,
        STAGE30_11_22_ADAPTER_MODULE,
        STAGE30_11_22_FAKE_PROOF_MODULE,
        "PHX2.stage30.stage30_11_21_migration_time_enrichment_adapter",
        "PHX2.stage30.stage30_11_18_harvested_facts_models",
        "PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models",
        "PHX2.stage30.stage30_11_15_ping_dedupe_ledger",
        "PHX2.stage30.stage30_11_6_candidate_harvest_adapter",
        "PHX2.stage30.stage30_11_6_candidate_source_models",
        "PHX2.stage30.stage30_11_5_fake_live_wiring_proof",
    )
    for module in STAGE30_11_22_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_22_ALLOWED_PHX2_IMPORTS)
    assert "stage27" not in joined
    assert "stage28" not in joined
    assert "stage29" not in joined
    assert "stage30_4_3" not in joined
    assert "birdeye" not in joined
    assert "stage30_11_11" not in joined
    assert "stage30_11_16" not in joined


# ---------------------------------------------------------------------------
# 4. Bounded caps mirror the committed harvest + session ceilings
# ---------------------------------------------------------------------------


def test_caps_pinned_and_mirror_committed_ceilings() -> None:
    assert STAGE30_11_22_MAX_HARVEST_HARD_CAP == 10
    assert STAGE30_11_22_MAX_HARVEST_HARD_CAP == STAGE30_11_6_MAX_HARVEST_HARD_CAP
    assert STAGE30_11_22_MAX_CANDIDATES_HARD_CAP == 10
    assert STAGE30_11_22_MAX_CANDIDATES_HARD_CAP == (
        STAGE30_11_17_MAX_CANDIDATES_HARD_CAP
    )


# ---------------------------------------------------------------------------
# 5. Bridge sentinels + verbatim / sentinel field sets (mirrored)
# ---------------------------------------------------------------------------


def test_sentinels_pinned_and_match_models() -> None:
    assert STAGE30_11_22_PENDING_ENRICHMENT == "PENDING_ENRICHMENT"
    assert STAGE30_11_22_PENDING_ENRICHMENT == MODELS_PENDING
    assert STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS == "PENDING"
    assert STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS == MODELS_PENDING_MC
    # The market-context sentinel must NOT be the dispatch-eligible PRESENT value.
    assert STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS != "PRESENT"


def test_bridge_field_sets_are_disjoint_facts_fields() -> None:
    facts_field_names = {
        f.name for f in dataclass_fields(Stage30_11_18HarvestedCandidateFacts)
    }
    verbatim = set(STAGE30_11_22_BRIDGE_VERBATIM_FIELDS)
    sentinel = set(STAGE30_11_22_BRIDGE_SENTINEL_FIELDS)
    # Every named field exists on the committed facts type.
    assert verbatim <= facts_field_names
    assert sentinel <= facts_field_names
    # The verbatim identity and the sentinel-filled fields are disjoint.
    assert verbatim & sentinel == set()
    # The real on-chain identity is carried verbatim.
    assert STAGE30_11_22_BRIDGE_VERBATIM_FIELDS == ("token_mint", "candidate_id")
    # The six fields the enrichment fills are the sentinel set.
    assert STAGE30_11_22_BRIDGE_SENTINEL_FIELDS == (
        "migration_time_utc",
        "current_price",
        "current_market_cap_usd",
        "liquidity_usd",
        "market_context_fetched_at_utc",
        "market_context_status",
    )


def test_redaction_statuses_pinned_and_match_models() -> None:
    assert STAGE30_11_22_REDACTION_STATUS_REDACTED == "REDACTED"
    assert STAGE30_11_22_REDACTION_STATUS_REDACTED == MODELS_REDACTED
    assert STAGE30_11_22_REDACTION_STATUSES == ("REDACTED", "REDACTION_VIOLATION")
    assert STAGE30_11_22_REDACTION_STATUSES == MODELS_REDACTION_STATUSES


# ---------------------------------------------------------------------------
# 6. Dataclass field tuples (mirrored)
# ---------------------------------------------------------------------------


def test_field_tuples_pinned_and_match_models() -> None:
    assert STAGE30_11_22_NO_REAL_SEND_ATTESTATION_FIELDS == (
        no_real_send_attestation_field_names()
    )
    assert STAGE30_11_22_REAL_FED_DRY_RUN_REPORT_FIELDS == (
        real_fed_dry_run_report_field_names()
    )


def test_report_fields_cover_the_required_operator_surface() -> None:
    report_fields = set(STAGE30_11_22_REAL_FED_DRY_RUN_REPORT_FIELDS)
    for required in (
        "events_seen",
        "candidates_harvested",
        "base_facts_built",
        "migration_skip_histogram",
        "price_skip_histogram",
        "market_skip_histogram",
        "projected",
        "rejected_projection",
        "composed",
        "dispatched",
        "dedupe_blocked",
        "would_send_recorded",
        "stop_reason",
        "redaction_status",
        "attestation",
    ):
        assert required in report_fields, (
            f"Stage 30.11.22 report must surface {required!r}"
        )


def test_attestation_fields_carry_no_body_or_secret() -> None:
    for name in STAGE30_11_22_NO_REAL_SEND_ATTESTATION_FIELDS:
        lower = name.lower()
        for forbidden in ("url", "secret", "webhook", "body"):
            assert forbidden not in lower, (
                f"Stage 30.11.22 attestation field {name!r} carries forbidden "
                f"substring {forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces + next allowed stage + operator-auth note
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_22_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_22_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_22_FORBIDDEN_SURFACES)
    for token in (
        "harvested-projection field fabrication",
        "bridge sentinel leak to composer",
        "trusted base migration_confirmed flag",
        "Stage 30.4.3 source import",
        "Stage 30.11.11 migration-anchored ATH import",
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
            f"Stage 30.11.22 forbidden surfaces must name {token!r}"
        )


def test_next_allowed_stage_is_the_separate_ceremony_steps() -> None:
    assert STAGE30_11_22_NEXT_ALLOWED_STAGE == (
        "operator-authorized real-fed dry-run ceremony + capped private send "
        "(separate steps)"
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_22_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True
    assert isinstance(STAGE30_11_22_LIVE_CEREMONY_NOTE, str)
    assert STAGE30_11_22_LIVE_CEREMONY_NOTE != ""


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the surface + earlier sections survive
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_22_surface() -> None:
    for name in (
        "STAGE30_11_22_MINOR_VERSION",
        "STAGE30_11_22_REPORT_SCHEMA_VERSION",
        "STAGE30_11_22_SOURCE_STAGE",
        "STAGE30_11_22_SPEC_LOCK_FILENAME",
        "STAGE30_11_22_SPEC_LOCK_PATH_PARTS",
        "STAGE30_11_22_MODELS_BASENAME",
        "STAGE30_11_22_ADAPTER_BASENAME",
        "STAGE30_11_22_FAKE_PROOF_BASENAME",
        "STAGE30_11_22_MODELS_MODULE",
        "STAGE30_11_22_ADAPTER_MODULE",
        "STAGE30_11_22_FAKE_PROOF_MODULE",
        "STAGE30_11_22_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_22_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_22_TEST_BASENAMES",
        "STAGE30_11_22_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_22_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_22_MAX_HARVEST_HARD_CAP",
        "STAGE30_11_22_MAX_CANDIDATES_HARD_CAP",
        "STAGE30_11_22_PENDING_ENRICHMENT",
        "STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS",
        "STAGE30_11_22_BRIDGE_VERBATIM_FIELDS",
        "STAGE30_11_22_BRIDGE_SENTINEL_FIELDS",
        "STAGE30_11_22_REDACTION_STATUS_REDACTED",
        "STAGE30_11_22_REDACTION_STATUSES",
        "STAGE30_11_22_NO_REAL_SEND_ATTESTATION_FIELDS",
        "STAGE30_11_22_REAL_FED_DRY_RUN_REPORT_FIELDS",
        "STAGE30_11_22_NEXT_ALLOWED_STAGE",
        "STAGE30_11_22_FORBIDDEN_SURFACES",
        "STAGE30_11_22_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_22_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_sections_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_18_MINOR_VERSION",
        "STAGE30_11_20_MINOR_VERSION",
        "STAGE30_11_21_MINOR_VERSION",
        "STAGE30_11_21_LIVE_CEREMONY_NOTE",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__
