"""Stage 30.11.18 manifest pin tests.

Pins the Stage 30.11.18 manifest constants (minor version, report schema version,
source stage, the three production basenames + module paths, the test basenames,
the stdlib + PHX2 import allowlists, the bounded caps, the closed-set Layer-1
projection decision + redaction vocabularies, the dataclass field tuples, the
forbidden surfaces, the next-allowed-stage pointer, the operator-auth note),
cross-checks the mirrored values against the Stage 30.11.18 models module + the
committed Stage 30.11.13 composer request, asserts the production + test files
exist, and confirms the manifest __all__ exports the surface while the earlier
sections survive.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_18_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_18_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_18_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_18_DEFAULT_MAX_CANDIDATES,
    STAGE30_11_18_FAKE_HARVEST_SESSION_PROOF_BASENAME,
    STAGE30_11_18_FAKE_HARVEST_SESSION_PROOF_MODULE,
    STAGE30_11_18_FORBIDDEN_SURFACES,
    STAGE30_11_18_HARVEST_TO_CURATED_ADAPTER_BASENAME,
    STAGE30_11_18_HARVEST_TO_CURATED_ADAPTER_MODULE,
    STAGE30_11_18_HARVESTED_FACTS_FIELDS,
    STAGE30_11_18_HARVESTED_FACTS_MODELS_BASENAME,
    STAGE30_11_18_HARVESTED_FACTS_MODELS_MODULE,
    STAGE30_11_18_LIVE_CEREMONY_NOTE,
    STAGE30_11_18_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_18_MAX_CANDIDATES_HARD_CAP,
    STAGE30_11_18_MINOR_VERSION,
    STAGE30_11_18_NEXT_ALLOWED_STAGE,
    STAGE30_11_18_PROJECTION_DECISIONS,
    STAGE30_11_18_PROJECTION_EVENT_FIELDS,
    STAGE30_11_18_REDACTION_STATUS_REDACTED,
    STAGE30_11_18_REDACTION_STATUSES,
    STAGE30_11_18_REPORT_SCHEMA_VERSION,
    STAGE30_11_18_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_18_SESSION_REPORT_FIELDS,
    STAGE30_11_18_SOURCE_STAGE,
    STAGE30_11_18_TEST_BASENAMES,
)
from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    Stage30_11_13RevalidationRequest,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    STAGE30_11_17_MAX_CANDIDATES_HARD_CAP,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    STAGE30_11_18_MINOR_VERSION as MODELS_MINOR,
    STAGE30_11_18_PROJECTION_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_18_REDACTION_STATUSES as MODELS_REDACTION_STATUSES,
    STAGE30_11_18_REDACTION_STATUS_REDACTED as MODELS_REDACTED,
    STAGE30_11_18_REPORT_SCHEMA_VERSION as MODELS_SCHEMA,
    STAGE30_11_18_SOURCE_STAGE as MODELS_SOURCE_STAGE,
    harvested_facts_field_names,
    projection_event_field_names,
    session_report_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
DOCS_ROOT: Path = PHX2_ROOT / "docs"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_18_MINOR_VERSION == "30.11.18"
    assert STAGE30_11_18_MINOR_VERSION == MODELS_MINOR


def test_schema_version_and_source_stage_match_models() -> None:
    assert STAGE30_11_18_REPORT_SCHEMA_VERSION == (
        "stage30_11_18_v0_harvested_facts_curated_session"
    )
    assert STAGE30_11_18_REPORT_SCHEMA_VERSION == MODELS_SCHEMA
    assert STAGE30_11_18_SOURCE_STAGE == "30.11.18"
    assert STAGE30_11_18_SOURCE_STAGE == MODELS_SOURCE_STAGE


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory + files exist
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_18_HARVESTED_FACTS_MODELS_BASENAME == (
        "stage30_11_18_harvested_facts_models.py"
    )
    assert STAGE30_11_18_HARVEST_TO_CURATED_ADAPTER_BASENAME == (
        "stage30_11_18_harvest_to_curated_adapter.py"
    )
    assert STAGE30_11_18_FAKE_HARVEST_SESSION_PROOF_BASENAME == (
        "stage30_11_18_fake_harvest_session_proof.py"
    )
    assert STAGE30_11_18_HARVESTED_FACTS_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_18_harvested_facts_models"
    )
    assert STAGE30_11_18_HARVEST_TO_CURATED_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_18_harvest_to_curated_adapter"
    )
    assert STAGE30_11_18_FAKE_HARVEST_SESSION_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_18_fake_harvest_session_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_18_HARVESTED_FACTS_MODELS_BASENAME,
        STAGE30_11_18_HARVEST_TO_CURATED_ADAPTER_BASENAME,
        STAGE30_11_18_FAKE_HARVEST_SESSION_PROOF_BASENAME,
    )
    assert STAGE30_11_18_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_18_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_18_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.18 requires {basename}"
        )


def test_spec_lock_doc_exists() -> None:
    assert (
        DOCS_ROOT
        / "STAGE_30_11_18_HARVESTED_FACTS_CURATED_SESSION_SPEC_LOCK.md"
    ).is_file()


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_18_TEST_BASENAMES == (
        "test_stage_30_11_18_harvest_to_curated_adapter.py",
        "test_stage_30_11_18_fake_harvest_session_proof.py",
        "test_stage_30_11_18_boundaries.py",
        "test_stage_30_11_18_manifest.py",
    )
    for basename in STAGE30_11_18_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.18 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists (stdlib + PHX2)
# ---------------------------------------------------------------------------


def test_stdlib_allowlist_pinned() -> None:
    assert STAGE30_11_18_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    # ``decimal`` is admitted (Layer-1 positivity); io / db / clock are not.
    assert "decimal" in STAGE30_11_18_ALLOWED_STDLIB_IMPORTS
    for forbidden in ("os", "json", "pathlib", "datetime", "sqlite3", "time"):
        assert forbidden not in STAGE30_11_18_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_within_family_no_stage28_29_16_or_harvest() -> None:
    assert STAGE30_11_18_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_18_HARVESTED_FACTS_MODELS_MODULE,
        STAGE30_11_18_HARVEST_TO_CURATED_ADAPTER_MODULE,
        STAGE30_11_18_FAKE_HARVEST_SESSION_PROOF_MODULE,
        "PHX2.stage30.stage30_11_13_committed_no_send_composer",
        "PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models",
        "PHX2.stage30.stage30_11_17_operator_curated_compose_session",
        "PHX2.stage30.stage30_11_15_ping_dedupe_ledger",
        "PHX2.stage30.stage30_11_5_fake_live_wiring_proof",
    )
    for module in STAGE30_11_18_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_18_ALLOWED_PHX2_IMPORTS)
    assert "stage28" not in joined
    assert "stage30_11_16" not in joined
    assert "candidate_harvest" not in joined
    assert "stage30_11_6_" not in joined


# ---------------------------------------------------------------------------
# 4. Bounded caps + closed-set vocabularies (mirrored)
# ---------------------------------------------------------------------------


def test_caps_pinned_and_mirror_committed_session() -> None:
    assert STAGE30_11_18_MAX_CANDIDATES_HARD_CAP == 10
    assert STAGE30_11_18_MAX_CANDIDATES_HARD_CAP == (
        STAGE30_11_17_MAX_CANDIDATES_HARD_CAP
    )
    assert STAGE30_11_18_DEFAULT_MAX_CANDIDATES == 10


def test_projection_decisions_pinned_and_match_models() -> None:
    assert STAGE30_11_18_PROJECTION_DECISIONS[0] == "PROJECTED"
    assert len(STAGE30_11_18_PROJECTION_DECISIONS) == 20
    assert STAGE30_11_18_PROJECTION_DECISIONS == MODELS_DECISIONS
    # Every decision past the first is a closed-set REJECTED_* token.
    for decision in STAGE30_11_18_PROJECTION_DECISIONS[1:]:
        assert decision.startswith("REJECTED_")
    # The four dispatch-critical missing-field tokens are present.
    for token in (
        "REJECTED_MISSING_CURRENT_PRICE",
        "REJECTED_MISSING_MIGRATION_TIME_UTC",
        "REJECTED_MISSING_LIQUIDITY_USD",
        "REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT",
    ):
        assert token in STAGE30_11_18_PROJECTION_DECISIONS


def test_redaction_statuses_pinned_and_match_models() -> None:
    assert STAGE30_11_18_REDACTION_STATUS_REDACTED == "REDACTED"
    assert STAGE30_11_18_REDACTION_STATUS_REDACTED == MODELS_REDACTED
    assert STAGE30_11_18_REDACTION_STATUSES == ("REDACTED", "REDACTION_VIOLATION")
    assert STAGE30_11_18_REDACTION_STATUSES == MODELS_REDACTION_STATUSES


# ---------------------------------------------------------------------------
# 5. Dataclass field tuples (mirrored from the models field-name helpers)
# ---------------------------------------------------------------------------


def test_field_tuples_pinned_and_match_models() -> None:
    assert STAGE30_11_18_HARVESTED_FACTS_FIELDS == harvested_facts_field_names()
    assert STAGE30_11_18_PROJECTION_EVENT_FIELDS == projection_event_field_names()
    assert STAGE30_11_18_SESSION_REPORT_FIELDS == session_report_field_names()


def test_harvested_facts_fields_match_committed_request_inputs() -> None:
    # The facts carrier carries EXACTLY the committed Stage 30.11.13 revalidation
    # request inputs (the adapter is a near 1:1 map).
    request_field_names = {
        f.name for f in dataclass_fields(Stage30_11_13RevalidationRequest)
    }
    assert set(STAGE30_11_18_HARVESTED_FACTS_FIELDS) == request_field_names


def test_projection_event_and_report_fields_carry_no_body_url_or_secret() -> None:
    for name in (
        STAGE30_11_18_PROJECTION_EVENT_FIELDS
        + STAGE30_11_18_SESSION_REPORT_FIELDS
    ):
        lower = name.lower()
        for forbidden in ("url", "secret", "webhook", "body", "price", "cap"):
            assert forbidden not in lower, (
                f"Stage 30.11.18 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. Forbidden surfaces + next allowed stage + operator-auth note
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_18_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_18_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_18_FORBIDDEN_SURFACES)
    for token in (
        "committed real harvest runner",
        "Stage 30.11.16 real-send guard call",
        "real transport",
        "real send",
        "Discord send",
        "env read",
        "live run",
        "live provider call",
        "Stage 28 direct import",
        "Stage 29 live provider import",
        "Stage 30.11.6 harvest adapter import",
        "while daemon",
        "operator ceremony ledger mutation",
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
            f"Stage 30.11.18 forbidden surfaces must name {token!r}"
        )


def test_next_allowed_stage_is_the_separate_ceremony() -> None:
    assert STAGE30_11_18_NEXT_ALLOWED_STAGE == (
        "operator-authorized ceremony-injected real harvest + enrichment "
        "(separate step)"
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_18_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True
    assert isinstance(STAGE30_11_18_LIVE_CEREMONY_NOTE, str)
    assert STAGE30_11_18_LIVE_CEREMONY_NOTE != ""


# ---------------------------------------------------------------------------
# 7. Manifest __all__ exports the surface + earlier sections survive
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_18_surface() -> None:
    for name in (
        "STAGE30_11_18_MINOR_VERSION",
        "STAGE30_11_18_REPORT_SCHEMA_VERSION",
        "STAGE30_11_18_SOURCE_STAGE",
        "STAGE30_11_18_SPEC_LOCK_FILENAME",
        "STAGE30_11_18_SPEC_LOCK_PATH_PARTS",
        "STAGE30_11_18_HARVESTED_FACTS_MODELS_BASENAME",
        "STAGE30_11_18_HARVEST_TO_CURATED_ADAPTER_BASENAME",
        "STAGE30_11_18_FAKE_HARVEST_SESSION_PROOF_BASENAME",
        "STAGE30_11_18_HARVESTED_FACTS_MODELS_MODULE",
        "STAGE30_11_18_HARVEST_TO_CURATED_ADAPTER_MODULE",
        "STAGE30_11_18_FAKE_HARVEST_SESSION_PROOF_MODULE",
        "STAGE30_11_18_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_18_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_18_TEST_BASENAMES",
        "STAGE30_11_18_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_18_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_18_MAX_CANDIDATES_HARD_CAP",
        "STAGE30_11_18_DEFAULT_MAX_CANDIDATES",
        "STAGE30_11_18_PROJECTION_DECISIONS",
        "STAGE30_11_18_REDACTION_STATUS_REDACTED",
        "STAGE30_11_18_REDACTION_STATUSES",
        "STAGE30_11_18_HARVESTED_FACTS_FIELDS",
        "STAGE30_11_18_PROJECTION_EVENT_FIELDS",
        "STAGE30_11_18_SESSION_REPORT_FIELDS",
        "STAGE30_11_18_NEXT_ALLOWED_STAGE",
        "STAGE30_11_18_FORBIDDEN_SURFACES",
        "STAGE30_11_18_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_18_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_sections_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_13_MINOR_VERSION",
        "STAGE30_11_15_MINOR_VERSION",
        "STAGE30_11_16_MINOR_VERSION",
        "STAGE30_11_17_MINOR_VERSION",
        "STAGE30_11_17_LIVE_CEREMONY_NOTE",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__
