"""Stage 30.11.16 manifest pin tests.

Pins the Stage 30.11.16 manifest constants (minor version, real-send schema
version, source stage, the three production basenames + module paths, the test
basenames, the stdlib + PHX2 import allowlists, the locked guardrail constants,
the closed-set decision / reason tokens, the dataclass field tuples, the
required dispatched compose-decision mirror, the forbidden surfaces, the
operator-auth live-ceremony note), cross-checks the mirrored values against the
Stage 30.11.16 models module + the committed Stage 30.11.13 composer, asserts the
production + test files exist, and confirms the manifest __all__ exports the
surface while the earlier sections survive.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_16_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_16_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_16_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_16_AUTH_CONFIRM_TOKEN,
    STAGE30_11_16_AUTH_SENTINEL_FIELDS,
    STAGE30_11_16_FAKE_REAL_SEND_PROOF_BASENAME,
    STAGE30_11_16_FAKE_REAL_SEND_PROOF_MODULE,
    STAGE30_11_16_FORBIDDEN_SURFACES,
    STAGE30_11_16_LIVE_CEREMONY_NOTE,
    STAGE30_11_16_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_16_MAX_DISPATCHES,
    STAGE30_11_16_MINOR_VERSION,
    STAGE30_11_16_NEXT_ALLOWED_STAGE,
    STAGE30_11_16_PAYLOAD_CONTENT_KEY,
    STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY,
    STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY,
    STAGE30_11_16_REAL_PRIVATE_TRANSPORT_GUARD_BASENAME,
    STAGE30_11_16_REAL_PRIVATE_TRANSPORT_GUARD_MODULE,
    STAGE30_11_16_REAL_SEND_DECISIONS,
    STAGE30_11_16_REAL_SEND_MODELS_BASENAME,
    STAGE30_11_16_REAL_SEND_MODELS_MODULE,
    STAGE30_11_16_REAL_SEND_REASONS,
    STAGE30_11_16_REAL_SEND_RESULT_FIELDS,
    STAGE30_11_16_REAL_SEND_SCHEMA_VERSION,
    STAGE30_11_16_REQUIRED_COMPOSE_DECISION,
    STAGE30_11_16_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_16_SOURCE_STAGE,
    STAGE30_11_16_TEST_BASENAMES,
    STAGE30_11_16_TRANSPORT_TARGET_FIELDS,
)
from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_DECISION_DISPATCHED,
)
from PHX2.stage30.stage30_11_16_real_send_models import (
    STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN as MODELS_CONFIRM_TOKEN,
    STAGE30_11_16_MINOR_VERSION as MODELS_MINOR,
    STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY as MODELS_IDENTITY,
    STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY as MODELS_VISIBILITY,
    STAGE30_11_16_REAL_SEND_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_16_REAL_SEND_REASONS as MODELS_REASONS,
    STAGE30_11_16_REAL_SEND_SCHEMA_VERSION as MODELS_SCHEMA,
    STAGE30_11_16_REQUIRED_COMPOSE_DECISION as MODELS_REQUIRED_DECISION,
    STAGE30_11_16_SOURCE_STAGE as MODELS_SOURCE_STAGE,
    real_send_authorization_field_names,
    real_send_result_field_names,
    transport_target_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_16_MINOR_VERSION == "30.11.16"
    assert STAGE30_11_16_MINOR_VERSION == MODELS_MINOR


def test_schema_version_and_source_stage_match_models() -> None:
    assert STAGE30_11_16_REAL_SEND_SCHEMA_VERSION == (
        "stage30_11_16_v0_real_send_guard"
    )
    assert STAGE30_11_16_REAL_SEND_SCHEMA_VERSION == MODELS_SCHEMA
    assert STAGE30_11_16_SOURCE_STAGE == "30.11.16"
    assert STAGE30_11_16_SOURCE_STAGE == MODELS_SOURCE_STAGE


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory + files exist
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_16_REAL_SEND_MODELS_BASENAME == (
        "stage30_11_16_real_send_models.py"
    )
    assert STAGE30_11_16_REAL_PRIVATE_TRANSPORT_GUARD_BASENAME == (
        "stage30_11_16_real_private_transport_guard.py"
    )
    assert STAGE30_11_16_FAKE_REAL_SEND_PROOF_BASENAME == (
        "stage30_11_16_fake_real_send_proof.py"
    )
    assert STAGE30_11_16_REAL_SEND_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_16_real_send_models"
    )
    assert STAGE30_11_16_REAL_PRIVATE_TRANSPORT_GUARD_MODULE == (
        "PHX2.stage30.stage30_11_16_real_private_transport_guard"
    )
    assert STAGE30_11_16_FAKE_REAL_SEND_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_16_fake_real_send_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_16_REAL_SEND_MODELS_BASENAME,
        STAGE30_11_16_REAL_PRIVATE_TRANSPORT_GUARD_BASENAME,
        STAGE30_11_16_FAKE_REAL_SEND_PROOF_BASENAME,
    )
    assert STAGE30_11_16_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_16_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_16_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.16 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_16_TEST_BASENAMES == (
        "test_stage_30_11_16_real_send_models.py",
        "test_stage_30_11_16_real_private_transport_guard.py",
        "test_stage_30_11_16_fake_real_send_proof.py",
        "test_stage_30_11_16_boundaries.py",
        "test_stage_30_11_16_manifest.py",
    )
    for basename in STAGE30_11_16_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.16 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists (stdlib + PHX2)
# ---------------------------------------------------------------------------


def test_stdlib_allowlist_pinned() -> None:
    assert STAGE30_11_16_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    for forbidden in ("os", "json", "pathlib", "datetime", "decimal", "sqlite3"):
        assert forbidden not in STAGE30_11_16_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_within_family_and_no_stage28() -> None:
    assert STAGE30_11_16_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_16_REAL_SEND_MODELS_MODULE,
        STAGE30_11_16_REAL_PRIVATE_TRANSPORT_GUARD_MODULE,
        STAGE30_11_16_FAKE_REAL_SEND_PROOF_MODULE,
        "PHX2.stage30.stage30_11_15_no_send_dedupe_guard",
        "PHX2.stage30.stage30_11_15_ping_dedupe_models",
        "PHX2.stage30.stage30_11_13_committed_no_send_composer",
    )
    for module in STAGE30_11_16_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_16_ALLOWED_PHX2_IMPORTS)
    assert "stage28" not in joined


# ---------------------------------------------------------------------------
# 4. Locked guardrail constants + decisions / reasons (mirrored from models)
# ---------------------------------------------------------------------------


def test_locked_constants_pinned_and_match_models() -> None:
    assert STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY == "PRIVATE_OPERATOR_WEBHOOK"
    assert STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY == MODELS_IDENTITY
    assert STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY == "PRIVATE_OPERATOR_ONLY"
    assert STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY == MODELS_VISIBILITY
    assert STAGE30_11_16_PAYLOAD_CONTENT_KEY == "content"
    # The manifest mirror uses a needle-safe name; the VALUE matches the models.
    assert STAGE30_11_16_AUTH_CONFIRM_TOKEN == (
        "I_AUTHORIZE_ONE_REAL_PRIVATE_OPERATOR_SEND"
    )
    assert STAGE30_11_16_AUTH_CONFIRM_TOKEN == MODELS_CONFIRM_TOKEN
    assert STAGE30_11_16_MAX_DISPATCHES == 1


def test_required_compose_decision_mirrors_committed_composer() -> None:
    assert STAGE30_11_16_REQUIRED_COMPOSE_DECISION == "NO_SEND_DISPATCHED"
    assert STAGE30_11_16_REQUIRED_COMPOSE_DECISION == MODELS_REQUIRED_DECISION
    # The mirror must equal the committed composer's dispatched decision token.
    assert STAGE30_11_16_REQUIRED_COMPOSE_DECISION == COMPOSE_DECISION_DISPATCHED


def test_decisions_pinned_and_match_models() -> None:
    assert STAGE30_11_16_REAL_SEND_DECISIONS == (
        "WOULD_SEND_NO_TRANSPORT",
        "FORWARDED_TO_TRANSPORT",
        "REFUSED",
    )
    assert STAGE30_11_16_REAL_SEND_DECISIONS == MODELS_DECISIONS


def test_reasons_pinned_and_match_models() -> None:
    assert STAGE30_11_16_REAL_SEND_REASONS == (
        "WOULD_SEND_RECORDED_NO_TRANSPORT",
        "FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE",
        "NOT_AUTHORIZED",
        "INVALID_AUTHORIZATION_TYPE",
        "INVALID_COMPOSE_RESULT",
        "COMPOSE_NOT_DISPATCHED",
        "DEDUPE_NOT_ALLOWED",
        "SNAPSHOT_MISSING",
        "INVALID_SNAPSHOT_PROVENANCE",
        "BODY_MISSING",
        "INVALID_TARGET_IDENTITY",
        "FORBIDDEN_PAYLOAD_FIELD",
        "CAP_EXHAUSTED",
        "TRANSPORT_EXCEPTION",
    )
    assert STAGE30_11_16_REAL_SEND_REASONS == MODELS_REASONS


# ---------------------------------------------------------------------------
# 5. Dataclass field tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_field_tuples_pinned_and_match_models() -> None:
    assert STAGE30_11_16_AUTH_SENTINEL_FIELDS == (
        real_send_authorization_field_names()
    )
    assert STAGE30_11_16_TRANSPORT_TARGET_FIELDS == (
        transport_target_field_names()
    )
    assert STAGE30_11_16_REAL_SEND_RESULT_FIELDS == real_send_result_field_names()


def test_result_field_tuple_carries_no_body_url_or_secret() -> None:
    for name in STAGE30_11_16_REAL_SEND_RESULT_FIELDS:
        lower = name.lower()
        for forbidden in ("body", "url", "secret", "content"):
            assert forbidden not in lower, (
                f"Stage 30.11.16 result field {name!r} carries forbidden "
                f"substring {forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. Forbidden surfaces + next allowed stage + operator-auth note
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_16_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_16_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_16_FORBIDDEN_SURFACES)
    for token in (
        "real send by default",
        "real transport default",
        "composer real-transport edit",
        "Discord send",
        "webhook call",
        "env read",
        "live run",
        "Stage 28 direct import",
        "ATH anchoring edit",
        "market freshness edit",
        "dedupe key edit",
        "Stage 30.12 renderer edit",
        "tier band edit",
        "public routing",
        "subscriber routing",
        "wallet / signing",
        "url in result",
        "body echo in result",
        "second send",
        "commit",
        "tag",
        "push",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.16 forbidden surfaces must name {token!r}"
        )


def test_next_allowed_stage_is_the_separate_ceremony() -> None:
    assert STAGE30_11_16_NEXT_ALLOWED_STAGE == (
        "operator-authorized controlled live ceremony (separate step)"
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_16_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True
    assert isinstance(STAGE30_11_16_LIVE_CEREMONY_NOTE, str)
    assert STAGE30_11_16_LIVE_CEREMONY_NOTE != ""


# ---------------------------------------------------------------------------
# 7. Manifest __all__ exports the surface + earlier sections survive
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_16_surface() -> None:
    for name in (
        "STAGE30_11_16_MINOR_VERSION",
        "STAGE30_11_16_REAL_SEND_SCHEMA_VERSION",
        "STAGE30_11_16_SOURCE_STAGE",
        "STAGE30_11_16_REAL_SEND_MODELS_BASENAME",
        "STAGE30_11_16_REAL_PRIVATE_TRANSPORT_GUARD_BASENAME",
        "STAGE30_11_16_FAKE_REAL_SEND_PROOF_BASENAME",
        "STAGE30_11_16_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_16_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_16_TEST_BASENAMES",
        "STAGE30_11_16_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_16_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY",
        "STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY",
        "STAGE30_11_16_PAYLOAD_CONTENT_KEY",
        "STAGE30_11_16_AUTH_CONFIRM_TOKEN",
        "STAGE30_11_16_REQUIRED_COMPOSE_DECISION",
        "STAGE30_11_16_MAX_DISPATCHES",
        "STAGE30_11_16_REAL_SEND_DECISIONS",
        "STAGE30_11_16_REAL_SEND_REASONS",
        "STAGE30_11_16_AUTH_SENTINEL_FIELDS",
        "STAGE30_11_16_TRANSPORT_TARGET_FIELDS",
        "STAGE30_11_16_REAL_SEND_RESULT_FIELDS",
        "STAGE30_11_16_NEXT_ALLOWED_STAGE",
        "STAGE30_11_16_FORBIDDEN_SURFACES",
        "STAGE30_11_16_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_16_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_sections_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_13_MINOR_VERSION",
        "STAGE30_11_15_MINOR_VERSION",
        "STAGE30_11_15_LIVE_CEREMONY_NOTE",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__
