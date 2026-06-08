"""Stage 30.11.15 manifest pin tests.

Pins the Stage 30.11.15 manifest constants (minor version, ping-dedupe + ledger
schema versions, source stage, key policy defaults, the four production
basenames + module paths, the committed sibling module paths, the inventory +
scanned + test basenames, the base + ledger stdlib allowlists, the PHX2 import
allowlist, the dedupe verdict / reason tokens, the key + ledger-record field
tuples, the composer dedupe reason mirrors, the forbidden surfaces, the
operator-auth live-ceremony note), cross-checks the mirrored values against the
Stage 30.11.15 models module + the committed Stage 30.11.13 composer, asserts the
production + test files exist, and confirms the manifest __all__ exports the
surface while the earlier sections survive.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_15_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_15_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_15_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_15_COMPOSER_DEDUPE_SUPPRESSED_REASON,
    STAGE30_11_15_COMPOSER_DEDUPE_UNAVAILABLE_REASON,
    STAGE30_11_15_DEDUPE_REASONS,
    STAGE30_11_15_DEDUPE_VERDICTS,
    STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT,
    STAGE30_11_15_DEFAULT_TTL_SECONDS,
    STAGE30_11_15_FAKE_DEDUPE_PROOF_BASENAME,
    STAGE30_11_15_FAKE_DEDUPE_PROOF_MODULE,
    STAGE30_11_15_FORBIDDEN_SURFACES,
    STAGE30_11_15_LEDGER_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_15_LEDGER_RECORD_FIELDS,
    STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION,
    STAGE30_11_15_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_15_MINOR_VERSION,
    STAGE30_11_15_NO_SEND_DEDUPE_GUARD_BASENAME,
    STAGE30_11_15_NO_SEND_DEDUPE_GUARD_MODULE,
    STAGE30_11_15_OPERATOR_SIGNAL_KIND,
    STAGE30_11_15_PING_DEDUPE_KEY_FIELDS,
    STAGE30_11_15_PING_DEDUPE_LEDGER_BASENAME,
    STAGE30_11_15_PING_DEDUPE_LEDGER_MODULE,
    STAGE30_11_15_PING_DEDUPE_MODELS_BASENAME,
    STAGE30_11_15_PING_DEDUPE_MODELS_MODULE,
    STAGE30_11_15_PING_DEDUPE_SCHEMA_VERSION,
    STAGE30_11_15_POLICY_VERSION,
    STAGE30_11_15_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_15_SOURCE_STAGE,
    STAGE30_11_15_TEST_BASENAMES,
)
from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_REJECTED_DEDUPE_SUPPRESSED,
    COMPOSE_REJECTED_DEDUPE_UNAVAILABLE,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    STAGE30_11_15_DEDUPE_REASONS as MODELS_REASONS,
    STAGE30_11_15_DEDUPE_VERDICTS as MODELS_VERDICTS,
    STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT as MODELS_BUCKET,
    STAGE30_11_15_DEFAULT_TTL_SECONDS as MODELS_TTL,
    STAGE30_11_15_LEDGER_RECORD_FIELDS as MODELS_LEDGER_FIELDS,
    STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION as MODELS_LEDGER_SCHEMA,
    STAGE30_11_15_MINOR_VERSION as MODELS_MINOR,
    STAGE30_11_15_OPERATOR_SIGNAL_KIND as MODELS_SIGNAL_KIND,
    STAGE30_11_15_PING_DEDUPE_SCHEMA_VERSION as MODELS_SCHEMA,
    STAGE30_11_15_POLICY_VERSION as MODELS_POLICY,
    STAGE30_11_15_SOURCE_STAGE as MODELS_SOURCE_STAGE,
    ping_dedupe_key_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_15_MINOR_VERSION == "30.11.15"
    assert STAGE30_11_15_MINOR_VERSION == MODELS_MINOR


def test_schema_versions_pinned_and_match_models() -> None:
    assert STAGE30_11_15_PING_DEDUPE_SCHEMA_VERSION == (
        "stage30_11_15_v0_ping_dedupe"
    )
    assert STAGE30_11_15_PING_DEDUPE_SCHEMA_VERSION == MODELS_SCHEMA
    assert STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION == (
        "stage30_11_15_v0_ping_dedupe_ledger"
    )
    assert STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION == MODELS_LEDGER_SCHEMA
    assert STAGE30_11_15_SOURCE_STAGE == "30.11.15"
    assert STAGE30_11_15_SOURCE_STAGE == MODELS_SOURCE_STAGE


def test_key_policy_defaults_pinned_and_match_models() -> None:
    assert STAGE30_11_15_OPERATOR_SIGNAL_KIND == "PHOENIX_OPERATOR_DIP_PING"
    assert STAGE30_11_15_OPERATOR_SIGNAL_KIND == MODELS_SIGNAL_KIND
    assert STAGE30_11_15_POLICY_VERSION == "stage30_11_15_v0"
    assert STAGE30_11_15_POLICY_VERSION == MODELS_POLICY
    assert STAGE30_11_15_DEFAULT_TTL_SECONDS == 21600
    assert STAGE30_11_15_DEFAULT_TTL_SECONDS == MODELS_TTL
    assert STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT == 10
    assert STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT == MODELS_BUCKET


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory + files exist
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_15_PING_DEDUPE_MODELS_BASENAME == (
        "stage30_11_15_ping_dedupe_models.py"
    )
    assert STAGE30_11_15_PING_DEDUPE_LEDGER_BASENAME == (
        "stage30_11_15_ping_dedupe_ledger.py"
    )
    assert STAGE30_11_15_NO_SEND_DEDUPE_GUARD_BASENAME == (
        "stage30_11_15_no_send_dedupe_guard.py"
    )
    assert STAGE30_11_15_FAKE_DEDUPE_PROOF_BASENAME == (
        "stage30_11_15_fake_dedupe_proof.py"
    )
    assert STAGE30_11_15_PING_DEDUPE_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_15_ping_dedupe_models"
    )
    assert STAGE30_11_15_PING_DEDUPE_LEDGER_MODULE == (
        "PHX2.stage30.stage30_11_15_ping_dedupe_ledger"
    )
    assert STAGE30_11_15_NO_SEND_DEDUPE_GUARD_MODULE == (
        "PHX2.stage30.stage30_11_15_no_send_dedupe_guard"
    )
    assert STAGE30_11_15_FAKE_DEDUPE_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_15_fake_dedupe_proof"
    )


def test_allowed_and_scanned_basenames_are_the_four_modules() -> None:
    expected = (
        STAGE30_11_15_PING_DEDUPE_MODELS_BASENAME,
        STAGE30_11_15_PING_DEDUPE_LEDGER_BASENAME,
        STAGE30_11_15_NO_SEND_DEDUPE_GUARD_BASENAME,
        STAGE30_11_15_FAKE_DEDUPE_PROOF_BASENAME,
    )
    assert STAGE30_11_15_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_15_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_15_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.15 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_15_TEST_BASENAMES == (
        "test_stage_30_11_15_ping_dedupe_ledger.py",
        "test_stage_30_11_15_no_send_dedupe_guard.py",
        "test_stage_30_11_15_boundaries.py",
        "test_stage_30_11_15_manifest.py",
        "test_stage_30_11_15_fake_dedupe_proof.py",
    )
    for basename in STAGE30_11_15_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.15 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists (base + ledger + PHX2)
# ---------------------------------------------------------------------------


def test_base_stdlib_allowlist_pinned() -> None:
    assert STAGE30_11_15_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    for forbidden in ("os", "json", "pathlib", "datetime", "sqlite3"):
        assert forbidden not in STAGE30_11_15_ALLOWED_STDLIB_IMPORTS


def test_ledger_stdlib_allowlist_pinned() -> None:
    assert STAGE30_11_15_LEDGER_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "json",
        "pathlib",
        "datetime",
    )
    # NO ``os`` (globally forbidden in Stage 30; the ledger appends via
    # ``Path.open``), NO database / compression / network surface.
    for forbidden in ("os", "sqlite3", "zstandard", "shutil", "time", "socket"):
        assert forbidden not in STAGE30_11_15_LEDGER_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_within_family() -> None:
    assert STAGE30_11_15_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_15_PING_DEDUPE_MODELS_MODULE,
        STAGE30_11_15_PING_DEDUPE_LEDGER_MODULE,
        STAGE30_11_15_NO_SEND_DEDUPE_GUARD_MODULE,
        "PHX2.stage30.stage30_11_13_committed_no_send_composer",
        "PHX2.stage30.stage30_11_13_fake_composer_proof",
        "PHX2.stage30.stage30_11_5_fake_live_wiring_proof",
    )
    for module in STAGE30_11_15_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_15_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Verdicts + reasons (mirrored from models)
# ---------------------------------------------------------------------------


def test_verdicts_pinned_and_match_models() -> None:
    assert STAGE30_11_15_DEDUPE_VERDICTS == (
        "DEDUPE_ALLOWED",
        "DEDUPE_SUPPRESSED_DUPLICATE",
        "DEDUPE_UNAVAILABLE",
    )
    assert STAGE30_11_15_DEDUPE_VERDICTS == MODELS_VERDICTS


def test_reasons_pinned_and_match_models() -> None:
    assert STAGE30_11_15_DEDUPE_REASONS == (
        "DEDUPE_REASON_NEW_KEY",
        "DEDUPE_REASON_TTL_EXPIRED",
        "DEDUPE_REASON_DUPLICATE_WITHIN_TTL",
        "DEDUPE_REASON_LEDGER_UNAVAILABLE",
        "DEDUPE_REASON_LEDGER_CORRUPT",
        "DEDUPE_REASON_LEDGER_WRITE_FAILED",
        "DEDUPE_REASON_MALFORMED_KEY",
    )
    assert STAGE30_11_15_DEDUPE_REASONS == MODELS_REASONS


# ---------------------------------------------------------------------------
# 5. Key + ledger-record field tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_key_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_15_PING_DEDUPE_KEY_FIELDS == (
        "token_mint",
        "operator_signal_kind",
        "tier_token",
        "drawdown_band",
        "post_migration_ath_verified",
        "ath_source_stage",
        "policy_version",
    )
    assert STAGE30_11_15_PING_DEDUPE_KEY_FIELDS == ping_dedupe_key_field_names()
    # The key must NOT carry the run-to-run axes that would defeat suppression.
    for forbidden in (
        "candidate_id",
        "current_market_cap_usd",
        "ath_price",
        "created_at_utc",
        "drawdown_from_ath",
    ):
        assert forbidden not in STAGE30_11_15_PING_DEDUPE_KEY_FIELDS


def test_ledger_record_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_15_LEDGER_RECORD_FIELDS == (
        "schema_version",
        "token_mint",
        "operator_signal_kind",
        "tier_token",
        "drawdown_band",
        "post_migration_ath_verified",
        "ath_source_stage",
        "policy_version",
        "reserved_at_utc",
    )
    assert STAGE30_11_15_LEDGER_RECORD_FIELDS == MODELS_LEDGER_FIELDS


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        STAGE30_11_15_PING_DEDUPE_KEY_FIELDS + STAGE30_11_15_LEDGER_RECORD_FIELDS
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "webhook",
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
                f"Stage 30.11.15 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. Composer dedupe reason mirrors match the committed composer
# ---------------------------------------------------------------------------


def test_composer_dedupe_reason_mirrors_match_composer() -> None:
    assert STAGE30_11_15_COMPOSER_DEDUPE_SUPPRESSED_REASON == (
        COMPOSE_REJECTED_DEDUPE_SUPPRESSED
    )
    assert STAGE30_11_15_COMPOSER_DEDUPE_UNAVAILABLE_REASON == (
        COMPOSE_REJECTED_DEDUPE_UNAVAILABLE
    )


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces + operator-auth live-ceremony note
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_15_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_15_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_15_FORBIDDEN_SURFACES)
    for token in (
        "real dispatch sink",
        "real transport",
        "Discord send",
        "webhook call",
        "env read",
        "live run",
        "ATH anchoring edit",
        "market freshness edit",
        "Stage 30.12 renderer edit",
        "tier band edit",
        "default storage root",
        "repo-hardcoded ledger path",
        "public routing",
        "subscriber routing",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "commit",
        "tag",
        "push",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.15 forbidden surfaces must name {token!r}"
        )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_15_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the surface + earlier sections survive
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_15_surface() -> None:
    for name in (
        "STAGE30_11_15_MINOR_VERSION",
        "STAGE30_11_15_PING_DEDUPE_SCHEMA_VERSION",
        "STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION",
        "STAGE30_11_15_SOURCE_STAGE",
        "STAGE30_11_15_OPERATOR_SIGNAL_KIND",
        "STAGE30_11_15_POLICY_VERSION",
        "STAGE30_11_15_DEFAULT_TTL_SECONDS",
        "STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT",
        "STAGE30_11_15_PING_DEDUPE_MODELS_BASENAME",
        "STAGE30_11_15_PING_DEDUPE_LEDGER_BASENAME",
        "STAGE30_11_15_NO_SEND_DEDUPE_GUARD_BASENAME",
        "STAGE30_11_15_FAKE_DEDUPE_PROOF_BASENAME",
        "STAGE30_11_15_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_15_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_15_TEST_BASENAMES",
        "STAGE30_11_15_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_15_LEDGER_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_15_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_15_DEDUPE_VERDICTS",
        "STAGE30_11_15_DEDUPE_REASONS",
        "STAGE30_11_15_PING_DEDUPE_KEY_FIELDS",
        "STAGE30_11_15_LEDGER_RECORD_FIELDS",
        "STAGE30_11_15_COMPOSER_DEDUPE_SUPPRESSED_REASON",
        "STAGE30_11_15_COMPOSER_DEDUPE_UNAVAILABLE_REASON",
        "STAGE30_11_15_NEXT_ALLOWED_STAGE",
        "STAGE30_11_15_FORBIDDEN_SURFACES",
        "STAGE30_11_15_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_15_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_sections_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_1_MINOR_VERSION",
        "STAGE30_11_13_MINOR_VERSION",
        "STAGE30_11_13_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__
