"""Stage 30.11.17 manifest pin tests.

Pins the Stage 30.11.17 manifest constants (minor version, session schema version,
source stage, the three production basenames + module paths, the test basenames,
the stdlib + PHX2 import allowlists, the bounded caps, the closed-set outcome /
stop-reason / redaction vocabularies, the required dispatched-decision mirror, the
dataclass field tuples, the forbidden surfaces, the next-allowed-stage pointer,
the operator-auth live-ceremony note), cross-checks the mirrored values against
the Stage 30.11.17 models module + the committed Stage 30.11.13 composer, asserts
the production + test files exist, and confirms the manifest __all__ exports the
surface while the earlier sections survive.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_17_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_17_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_17_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_17_CANDIDATE_FIELDS,
    STAGE30_11_17_CANDIDATE_LIST_MODELS_BASENAME,
    STAGE30_11_17_CANDIDATE_LIST_MODELS_MODULE,
    STAGE30_11_17_COMPOSE_SESSION_BASENAME,
    STAGE30_11_17_COMPOSE_SESSION_MODULE,
    STAGE30_11_17_DEFAULT_MAX_CANDIDATES,
    STAGE30_11_17_ENTRY_OUTCOMES,
    STAGE30_11_17_FAKE_CURATED_SESSION_PROOF_BASENAME,
    STAGE30_11_17_FAKE_CURATED_SESSION_PROOF_MODULE,
    STAGE30_11_17_FORBIDDEN_SURFACES,
    STAGE30_11_17_LIVE_CEREMONY_NOTE,
    STAGE30_11_17_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_17_MAX_CANDIDATES_HARD_CAP,
    STAGE30_11_17_MINOR_VERSION,
    STAGE30_11_17_NEXT_ALLOWED_STAGE,
    STAGE30_11_17_REDACTION_STATUS_REDACTED,
    STAGE30_11_17_REDACTION_STATUSES,
    STAGE30_11_17_REQUIRED_COMPOSE_DISPATCH_DECISION,
    STAGE30_11_17_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_17_SESSION_CONFIG_FIELDS,
    STAGE30_11_17_SESSION_EVENT_FIELDS,
    STAGE30_11_17_SESSION_RESULT_FIELDS,
    STAGE30_11_17_SESSION_SCHEMA_VERSION,
    STAGE30_11_17_SOURCE_STAGE,
    STAGE30_11_17_STOP_REASONS,
    STAGE30_11_17_TEST_BASENAMES,
)
from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_DECISION_DISPATCHED,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    STAGE30_11_17_DEFAULT_MAX_CANDIDATES as MODELS_DEFAULT_MAX,
    STAGE30_11_17_ENTRY_OUTCOMES as MODELS_OUTCOMES,
    STAGE30_11_17_MAX_CANDIDATES_HARD_CAP as MODELS_HARD_CAP,
    STAGE30_11_17_MINOR_VERSION as MODELS_MINOR,
    STAGE30_11_17_REDACTION_STATUSES as MODELS_REDACTION_STATUSES,
    STAGE30_11_17_REDACTION_STATUS_REDACTED as MODELS_REDACTED,
    STAGE30_11_17_SESSION_SCHEMA_VERSION as MODELS_SCHEMA,
    STAGE30_11_17_SOURCE_STAGE as MODELS_SOURCE_STAGE,
    STAGE30_11_17_STOP_REASONS as MODELS_STOP_REASONS,
    operator_curated_candidate_field_names,
    session_config_field_names,
    session_event_field_names,
    session_result_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
DOCS_ROOT: Path = PHX2_ROOT / "docs"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_17_MINOR_VERSION == "30.11.17"
    assert STAGE30_11_17_MINOR_VERSION == MODELS_MINOR


def test_schema_version_and_source_stage_match_models() -> None:
    assert STAGE30_11_17_SESSION_SCHEMA_VERSION == (
        "stage30_11_17_v0_operator_curated_compose_session"
    )
    assert STAGE30_11_17_SESSION_SCHEMA_VERSION == MODELS_SCHEMA
    assert STAGE30_11_17_SOURCE_STAGE == "30.11.17"
    assert STAGE30_11_17_SOURCE_STAGE == MODELS_SOURCE_STAGE


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory + files exist
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_17_CANDIDATE_LIST_MODELS_BASENAME == (
        "stage30_11_17_operator_curated_candidate_list_models.py"
    )
    assert STAGE30_11_17_COMPOSE_SESSION_BASENAME == (
        "stage30_11_17_operator_curated_compose_session.py"
    )
    assert STAGE30_11_17_FAKE_CURATED_SESSION_PROOF_BASENAME == (
        "stage30_11_17_fake_curated_session_proof.py"
    )
    assert STAGE30_11_17_CANDIDATE_LIST_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models"
    )
    assert STAGE30_11_17_COMPOSE_SESSION_MODULE == (
        "PHX2.stage30.stage30_11_17_operator_curated_compose_session"
    )
    assert STAGE30_11_17_FAKE_CURATED_SESSION_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_17_fake_curated_session_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_17_CANDIDATE_LIST_MODELS_BASENAME,
        STAGE30_11_17_COMPOSE_SESSION_BASENAME,
        STAGE30_11_17_FAKE_CURATED_SESSION_PROOF_BASENAME,
    )
    assert STAGE30_11_17_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_17_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_17_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.17 requires {basename}"
        )


def test_spec_lock_doc_exists() -> None:
    assert (
        DOCS_ROOT / "STAGE_30_11_17_OPERATOR_CURATED_COMPOSE_SESSION_SPEC_LOCK.md"
    ).is_file()


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_17_TEST_BASENAMES == (
        "test_stage_30_11_17_operator_curated_candidate_list_models.py",
        "test_stage_30_11_17_operator_curated_compose_session.py",
        "test_stage_30_11_17_fake_curated_session_proof.py",
        "test_stage_30_11_17_boundaries.py",
        "test_stage_30_11_17_manifest.py",
    )
    for basename in STAGE30_11_17_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.17 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists (stdlib + PHX2)
# ---------------------------------------------------------------------------


def test_stdlib_allowlist_pinned() -> None:
    assert STAGE30_11_17_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    for forbidden in ("os", "json", "pathlib", "datetime", "decimal", "sqlite3"):
        assert forbidden not in STAGE30_11_17_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_within_family_no_stage28_29_16_or_harvest() -> None:
    assert STAGE30_11_17_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_17_CANDIDATE_LIST_MODELS_MODULE,
        STAGE30_11_17_COMPOSE_SESSION_MODULE,
        STAGE30_11_17_FAKE_CURATED_SESSION_PROOF_MODULE,
        "PHX2.stage30.stage30_11_13_committed_no_send_composer",
        "PHX2.stage30.stage30_11_15_no_send_dedupe_guard",
        "PHX2.stage30.stage30_11_15_ping_dedupe_ledger",
        "PHX2.stage30.stage30_11_5_fake_live_wiring_proof",
    )
    for module in STAGE30_11_17_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_17_ALLOWED_PHX2_IMPORTS)
    assert "stage28" not in joined
    # No Stage 30.11.16 real-send guard, no Stage 30.11.6 real harvest adapter.
    assert "stage30_11_16" not in joined
    assert "candidate_harvest" not in joined
    assert "stage30_11_6_" not in joined


# ---------------------------------------------------------------------------
# 4. Bounded caps + closed-set vocabularies (mirrored from models)
# ---------------------------------------------------------------------------


def test_caps_pinned_and_match_models() -> None:
    assert STAGE30_11_17_MAX_CANDIDATES_HARD_CAP == 10
    assert STAGE30_11_17_MAX_CANDIDATES_HARD_CAP == MODELS_HARD_CAP
    assert STAGE30_11_17_DEFAULT_MAX_CANDIDATES == 10
    assert STAGE30_11_17_DEFAULT_MAX_CANDIDATES == MODELS_DEFAULT_MAX


def test_entry_outcomes_pinned_and_match_models() -> None:
    assert STAGE30_11_17_ENTRY_OUTCOMES == (
        "DISPATCHED",
        "REJECTED",
        "DEDUPE_BLOCKED",
        "ERROR",
    )
    assert STAGE30_11_17_ENTRY_OUTCOMES == MODELS_OUTCOMES


def test_stop_reasons_pinned_and_match_models() -> None:
    assert STAGE30_11_17_STOP_REASONS == (
        "COMPLETED_ALL_CANDIDATES",
        "STOPPED_BY_CANDIDATE_CAP",
        "STOPPED_BY_COMPOSITION_CAP",
    )
    assert STAGE30_11_17_STOP_REASONS == MODELS_STOP_REASONS


def test_redaction_statuses_pinned_and_match_models() -> None:
    assert STAGE30_11_17_REDACTION_STATUS_REDACTED == "REDACTED"
    assert STAGE30_11_17_REDACTION_STATUS_REDACTED == MODELS_REDACTED
    assert STAGE30_11_17_REDACTION_STATUSES == ("REDACTED", "REDACTION_VIOLATION")
    assert STAGE30_11_17_REDACTION_STATUSES == MODELS_REDACTION_STATUSES


def test_required_dispatch_decision_mirrors_committed_composer() -> None:
    assert STAGE30_11_17_REQUIRED_COMPOSE_DISPATCH_DECISION == "NO_SEND_DISPATCHED"
    # The mirror must equal the committed composer's dispatched decision token.
    assert STAGE30_11_17_REQUIRED_COMPOSE_DISPATCH_DECISION == (
        COMPOSE_DECISION_DISPATCHED
    )


# ---------------------------------------------------------------------------
# 5. Dataclass field tuples (mirrored from the models field-name helpers)
# ---------------------------------------------------------------------------


def test_field_tuples_pinned_and_match_models() -> None:
    assert STAGE30_11_17_CANDIDATE_FIELDS == (
        operator_curated_candidate_field_names()
    )
    assert STAGE30_11_17_SESSION_CONFIG_FIELDS == session_config_field_names()
    assert STAGE30_11_17_SESSION_EVENT_FIELDS == session_event_field_names()
    assert STAGE30_11_17_SESSION_RESULT_FIELDS == session_result_field_names()


def test_event_field_tuple_carries_no_body_url_or_secret() -> None:
    for name in STAGE30_11_17_SESSION_EVENT_FIELDS:
        lower = name.lower()
        for forbidden in ("url", "secret", "webhook", "content"):
            assert forbidden not in lower, (
                f"Stage 30.11.17 event field {name!r} carries forbidden "
                f"substring {forbidden!r}"
            )
        if "body" in lower:
            assert lower == "body_present"


# ---------------------------------------------------------------------------
# 6. Forbidden surfaces + next allowed stage + operator-auth note
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_17_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_17_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_17_FORBIDDEN_SURFACES)
    for token in (
        "real harvest adapter binding",
        "Stage 30.11.16 real-send guard call",
        "real transport",
        "real send",
        "Discord send",
        "webhook call",
        "env read",
        "live run",
        "live provider call",
        "Stage 28 direct import",
        "Stage 29 live provider import",
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
            f"Stage 30.11.17 forbidden surfaces must name {token!r}"
        )


def test_next_allowed_stage_is_the_separate_ceremony() -> None:
    assert STAGE30_11_17_NEXT_ALLOWED_STAGE == (
        "operator-authorized controlled live ceremony (separate step)"
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_17_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True
    assert isinstance(STAGE30_11_17_LIVE_CEREMONY_NOTE, str)
    assert STAGE30_11_17_LIVE_CEREMONY_NOTE != ""


# ---------------------------------------------------------------------------
# 7. Manifest __all__ exports the surface + earlier sections survive
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_17_surface() -> None:
    for name in (
        "STAGE30_11_17_MINOR_VERSION",
        "STAGE30_11_17_SESSION_SCHEMA_VERSION",
        "STAGE30_11_17_SOURCE_STAGE",
        "STAGE30_11_17_SPEC_LOCK_FILENAME",
        "STAGE30_11_17_SPEC_LOCK_PATH_PARTS",
        "STAGE30_11_17_CANDIDATE_LIST_MODELS_BASENAME",
        "STAGE30_11_17_COMPOSE_SESSION_BASENAME",
        "STAGE30_11_17_FAKE_CURATED_SESSION_PROOF_BASENAME",
        "STAGE30_11_17_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_17_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_17_TEST_BASENAMES",
        "STAGE30_11_17_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_17_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_17_MAX_CANDIDATES_HARD_CAP",
        "STAGE30_11_17_DEFAULT_MAX_CANDIDATES",
        "STAGE30_11_17_ENTRY_OUTCOMES",
        "STAGE30_11_17_STOP_REASONS",
        "STAGE30_11_17_REDACTION_STATUS_REDACTED",
        "STAGE30_11_17_REDACTION_STATUSES",
        "STAGE30_11_17_REQUIRED_COMPOSE_DISPATCH_DECISION",
        "STAGE30_11_17_CANDIDATE_FIELDS",
        "STAGE30_11_17_SESSION_CONFIG_FIELDS",
        "STAGE30_11_17_SESSION_EVENT_FIELDS",
        "STAGE30_11_17_SESSION_RESULT_FIELDS",
        "STAGE30_11_17_NEXT_ALLOWED_STAGE",
        "STAGE30_11_17_FORBIDDEN_SURFACES",
        "STAGE30_11_17_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_17_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_sections_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_13_MINOR_VERSION",
        "STAGE30_11_15_MINOR_VERSION",
        "STAGE30_11_16_MINOR_VERSION",
        "STAGE30_11_16_LIVE_CEREMONY_NOTE",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__
