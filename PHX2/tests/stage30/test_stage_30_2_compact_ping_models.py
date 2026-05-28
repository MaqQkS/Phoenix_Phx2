"""Stage 30.2 compact ping models tests.

Pure read-only tests over the Stage 30.2 closed-set surface, the
immutable record shapes, the forbidden-field-name guard, the error
class, the locked schema version, the locked artifact basename, the
body cap constants, and the ``DISPLAY_UNKNOWN`` sentinel. The tests
also AST-scan every Stage 30.2 production module to confirm there
is no forbidden import (no env / socket / network / Stage 21-29
production import).

Discipline: no env reads, no network, no Discord, no provider
calls. Stdlib + pytest only.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from PHX2.stage30 import compact_ping_models as M
from PHX2.stage30.tier_decision_models import (
    BASIS_PRICE,
    STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
    TIER_REASON_TIER_1_IN_BAND,
    TIER_TOKEN_TIER_1,
    TierDecisionRecord,
)


_STAGE30_2_PRODUCTION_BASENAMES: tuple = (
    "compact_ping_models.py",
    "compact_ping_renderer.py",
    "compact_ping_artifact_writer.py",
    "stage30_2_manifest.py",
)


def _make_tier_decision(**overrides: object) -> TierDecisionRecord:
    defaults: dict = {
        "schema_version": STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
        "session_id": None,
        "ping_id": None,
        "candidate_id": None,
        "mint": None,
        "basis": BASIS_PRICE,
        "drawdown_from_ath_raw": "0.55",
        "drop_positive": "0.55",
        "ath_status": "PRESENT",
        "ath_since_migration_status": "POST_MIGRATION_ONLY",
        "migration_status": "PRESENT",
        "tier_token": TIER_TOKEN_TIER_1,
        "tier_reason": TIER_REASON_TIER_1_IN_BAND,
        "created_at_utc": "2026-05-27T12:00:00Z",
    }
    defaults.update(overrides)
    return TierDecisionRecord(**defaults)


# ---------------------------------------------------------------------------
# Locked schema version + basename + cap pins
# ---------------------------------------------------------------------------


def test_minor_version_byte_pinned() -> None:
    assert M.STAGE30_2_MINOR_VERSION == "30.2"


def test_schema_version_byte_pinned() -> None:
    assert (
        M.STAGE30_2_COMPACT_PING_SCHEMA_VERSION
        == "stage30_2_v0_compact_ping"
    )


def test_artifact_basename_byte_pinned() -> None:
    assert (
        M.STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
        == "stage30_2_compact_pings.jsonl"
    )


def test_body_char_target_byte_pinned() -> None:
    assert M.STAGE30_2_BODY_CHAR_TARGET == 800


def test_body_char_hard_cap_byte_pinned() -> None:
    assert M.STAGE30_2_BODY_CHAR_HARD_CAP == 1900


def test_display_unknown_byte_pinned() -> None:
    assert M.DISPLAY_UNKNOWN == "Unknown"


# ---------------------------------------------------------------------------
# CompactPingInputRecord
# ---------------------------------------------------------------------------


_EXPECTED_INPUT_FIELDS: tuple = (
    "tier_decision",
    "mint",
    "symbol",
    "current_mc_text",
    "ath_mc_text",
    "migration_mc_text",
    "lp_text",
    "net_flow_text",
    "age_since_migration_seconds",
    "price_status",
    "session_id",
    "ping_id",
    "candidate_id",
    "created_at_utc",
)


def test_compact_ping_input_record_fields_exact() -> None:
    assert M.CompactPingInputRecord._fields == _EXPECTED_INPUT_FIELDS


def test_compact_ping_input_record_has_no_forbidden_field_names() -> None:
    for name in M.CompactPingInputRecord._fields:
        assert not M.is_forbidden_record_field_name(name), name


def test_compact_ping_input_record_construction_minimal() -> None:
    rec = M.CompactPingInputRecord(
        tier_decision=_make_tier_decision(),
        mint=None,
        symbol=None,
        current_mc_text=None,
        ath_mc_text=None,
        migration_mc_text=None,
        lp_text=None,
        net_flow_text=None,
        age_since_migration_seconds=None,
        price_status=None,
        session_id=None,
        ping_id=None,
        candidate_id=None,
        created_at_utc="2026-05-27T12:00:00Z",
    )
    assert rec.tier_decision.tier_token == "Tier 1"
    assert rec.created_at_utc == "2026-05-27T12:00:00Z"


def test_compact_ping_input_record_is_namedtuple_immutable() -> None:
    rec = M.CompactPingInputRecord(
        tier_decision=_make_tier_decision(),
        mint=None,
        symbol=None,
        current_mc_text=None,
        ath_mc_text=None,
        migration_mc_text=None,
        lp_text=None,
        net_flow_text=None,
        age_since_migration_seconds=None,
        price_status=None,
        session_id=None,
        ping_id=None,
        candidate_id=None,
        created_at_utc="2026-05-27T12:00:00Z",
    )
    with pytest.raises(AttributeError):
        rec.created_at_utc = (  # type: ignore[misc]
            "2026-05-28T12:00:00Z"
        )


# ---------------------------------------------------------------------------
# CompactPingSnapshotRecord
# ---------------------------------------------------------------------------


_EXPECTED_SNAPSHOT_FIELDS: tuple = (
    "schema_version",
    "session_id",
    "ping_id",
    "candidate_id",
    "mint",
    "symbol",
    "tier_token",
    "tier_reason",
    "basis",
    "drawdown_from_ath_raw",
    "drop_positive",
    "ath_status",
    "ath_since_migration_status",
    "migration_status",
    "price_status",
    "current_mc_display",
    "ath_mc_display",
    "migration_mc_display",
    "drop_percent_display",
    "age_display",
    "lp_display",
    "net_flow_display",
    "warnings",
    "body_text",
    "body_length_chars",
    "created_at_utc",
)


def test_compact_ping_snapshot_record_fields_exact() -> None:
    assert (
        M.CompactPingSnapshotRecord._fields
        == _EXPECTED_SNAPSHOT_FIELDS
    )


def test_compact_ping_snapshot_record_has_no_forbidden_field_names() -> (
    None
):
    for name in M.CompactPingSnapshotRecord._fields:
        assert not M.is_forbidden_record_field_name(name), name


def test_compact_ping_snapshot_record_construction_minimal() -> None:
    rec = M.CompactPingSnapshotRecord(
        schema_version=M.STAGE30_2_COMPACT_PING_SCHEMA_VERSION,
        session_id=None,
        ping_id=None,
        candidate_id=None,
        mint=None,
        symbol=None,
        tier_token="Tier 1",
        tier_reason="TIER_1_IN_BAND",
        basis="price-basis",
        drawdown_from_ath_raw="0.55",
        drop_positive="0.55",
        ath_status="PRESENT",
        ath_since_migration_status="POST_MIGRATION_ONLY",
        migration_status="PRESENT",
        price_status=None,
        current_mc_display=M.DISPLAY_UNKNOWN,
        ath_mc_display=M.DISPLAY_UNKNOWN,
        migration_mc_display=M.DISPLAY_UNKNOWN,
        drop_percent_display="-55%",
        age_display=M.DISPLAY_UNKNOWN,
        lp_display=M.DISPLAY_UNKNOWN,
        net_flow_display=M.DISPLAY_UNKNOWN,
        warnings=(),
        body_text="x",
        body_length_chars=1,
        created_at_utc="2026-05-27T12:00:00Z",
    )
    assert rec.tier_token == "Tier 1"
    assert rec.warnings == ()
    assert rec.body_length_chars == 1


def test_compact_ping_snapshot_record_is_namedtuple_immutable() -> None:
    rec = M.CompactPingSnapshotRecord(
        schema_version=M.STAGE30_2_COMPACT_PING_SCHEMA_VERSION,
        session_id=None,
        ping_id=None,
        candidate_id=None,
        mint=None,
        symbol=None,
        tier_token="Tier 1",
        tier_reason="TIER_1_IN_BAND",
        basis="price-basis",
        drawdown_from_ath_raw="0.55",
        drop_positive="0.55",
        ath_status="PRESENT",
        ath_since_migration_status="POST_MIGRATION_ONLY",
        migration_status="PRESENT",
        price_status=None,
        current_mc_display=M.DISPLAY_UNKNOWN,
        ath_mc_display=M.DISPLAY_UNKNOWN,
        migration_mc_display=M.DISPLAY_UNKNOWN,
        drop_percent_display="-55%",
        age_display=M.DISPLAY_UNKNOWN,
        lp_display=M.DISPLAY_UNKNOWN,
        net_flow_display=M.DISPLAY_UNKNOWN,
        warnings=(),
        body_text="x",
        body_length_chars=1,
        created_at_utc="2026-05-27T12:00:00Z",
    )
    with pytest.raises(AttributeError):
        rec.tier_token = "Tier 2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FORBIDDEN_RECORD_FIELD_NAMES
# ---------------------------------------------------------------------------


_EXPECTED_FORBIDDEN_FIELD_NAMES: tuple = (
    "webhook",
    "webhook_url",
    "webhooks",
    "webhook_token",
    "api_key",
    "apikey",
    "bearer",
    "bearer_token",
    "authorization",
    "secret",
    "secret_key",
    "secretkey",
    "token_secret",
    "private_key",
    "privatekey",
    "seed_phrase",
    "mnemonic",
    "signer",
    "signing_key",
    "credentials",
    "password",
    "raw_payload",
    "payload",
    "payload_blob",
    "payload_summary",
    "migration_event_id",
    "raw_capture_ref",
    "source_event_ref",
    "rpc_url",
)


def test_forbidden_record_field_names_exact() -> None:
    assert set(M.FORBIDDEN_RECORD_FIELD_NAMES) == set(
        _EXPECTED_FORBIDDEN_FIELD_NAMES
    )


def test_forbidden_record_field_names_all_strings_no_duplicates() -> None:
    assert len(M.FORBIDDEN_RECORD_FIELD_NAMES) == len(
        set(M.FORBIDDEN_RECORD_FIELD_NAMES)
    )
    for value in M.FORBIDDEN_RECORD_FIELD_NAMES:
        assert isinstance(value, str)
        assert value != ""


@pytest.mark.parametrize(
    "bad_name",
    [
        "webhook",
        "webhook_url",
        "api_key",
        "apikey",
        "bearer_token",
        "authorization",
        "secret",
        "secret_key",
        "private_key",
        "credentials",
        "raw_payload",
        "payload",
        "payload_blob",
        "migration_event_id",
        "raw_capture_ref",
        "source_event_ref",
        "rpc_url",
        "WEBHOOK",
        "API_KEY",
        "Bearer_Token",
        "x_webhook_url_y",
        "my_secret_value",
        "the_payload_summary_here",
    ],
)
def test_is_forbidden_record_field_name_accepts(bad_name: str) -> None:
    assert M.is_forbidden_record_field_name(bad_name)


@pytest.mark.parametrize(
    "ok_name",
    list(_EXPECTED_INPUT_FIELDS) + list(_EXPECTED_SNAPSHOT_FIELDS),
)
def test_is_forbidden_record_field_name_rejects_record_fields(
    ok_name: str,
) -> None:
    assert not M.is_forbidden_record_field_name(ok_name)


@pytest.mark.parametrize(
    "non_str",
    [None, 0, 0.0, [], {}, object(), True],
)
def test_is_forbidden_record_field_name_rejects_non_str(
    non_str: object,
) -> None:
    assert not M.is_forbidden_record_field_name(non_str)


# ---------------------------------------------------------------------------
# Stage30_2CompactPingError
# ---------------------------------------------------------------------------


def test_error_is_exception_subclass() -> None:
    assert issubclass(M.Stage30_2CompactPingError, Exception)


def test_error_carries_reason_attribute() -> None:
    err = M.Stage30_2CompactPingError("MY_REASON")
    assert err.reason == "MY_REASON"
    assert "MY_REASON" in str(err)


# ---------------------------------------------------------------------------
# Forbidden-imports AST scan over every Stage 30.2 production module
# ---------------------------------------------------------------------------


_FORBIDDEN_TOP_LEVEL_IMPORTS: tuple = (
    "os",
    "socket",
    "ssl",
    "urllib",
    "http",
    "httpx",
    "requests",
    "aiohttp",
    "grpc",
    "grpcio",
    "websockets",
    "websocket",
    "subprocess",
    "asyncio",
    "datetime",
    "time",
)


_FORBIDDEN_NAME_SUBSTRINGS: tuple = (
    "Phoenix_Bot",
    "phoenix_bot",
)


_FORBIDDEN_PHX2_PACKAGE_PREFIXES: tuple = (
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
    "PHX2.stage25",
    "PHX2.stage26",
    "PHX2.stage27",
    "PHX2.stage28",
    "PHX2.stage29",
)


def _stage30_2_production_module_paths() -> list:
    stage30_root = (
        Path(__file__).resolve().parent.parent.parent / "stage30"
    )
    paths: list = []
    for basename in _STAGE30_2_PRODUCTION_BASENAMES:
        candidate = stage30_root / basename
        assert candidate.is_file(), (
            f"missing Stage 30.2 production module: {candidate}"
        )
        paths.append(candidate)
    return paths


def _module_import_names(module_path: Path) -> list:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.append(node.module)
    return imports


def test_stage30_2_modules_have_no_forbidden_top_level_imports() -> None:
    for module_path in _stage30_2_production_module_paths():
        imports = _module_import_names(module_path)
        for imported in imports:
            top = imported.split(".")[0]
            assert top not in _FORBIDDEN_TOP_LEVEL_IMPORTS, (
                f"{module_path.name} imports forbidden top-level "
                f"module: {imported}"
            )


def test_stage30_2_modules_dont_carry_legacy_name_substrings() -> None:
    for module_path in _stage30_2_production_module_paths():
        text = module_path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_NAME_SUBSTRINGS:
            assert needle not in text, (
                f"{module_path.name} carries forbidden name "
                f"substring: {needle}"
            )


def test_stage30_2_modules_dont_import_other_phx2_stages() -> None:
    for module_path in _stage30_2_production_module_paths():
        imports = _module_import_names(module_path)
        for imported in imports:
            for prefix in _FORBIDDEN_PHX2_PACKAGE_PREFIXES:
                assert not imported.startswith(prefix), (
                    f"{module_path.name} imports forbidden Stage "
                    f"package: {imported}"
                )


def test_stage30_2_modules_only_phx2_dep_is_stage30() -> None:
    for module_path in _stage30_2_production_module_paths():
        imports = _module_import_names(module_path)
        for imported in imports:
            if imported.startswith("PHX2"):
                assert imported.startswith("PHX2.stage30."), (
                    f"{module_path.name} imports unexpected PHX2 "
                    f"module: {imported}"
                )


def test_stage30_2_modules_do_not_import_stage30_1_projector() -> None:
    for module_path in _stage30_2_production_module_paths():
        imports = _module_import_names(module_path)
        for imported in imports:
            assert imported != (
                "PHX2.stage30.tier_decision_projector"
            ), (
                f"{module_path.name} imports the Stage 30.1 "
                f"projector; Stage 30.2 must not depend on it"
            )


# ---------------------------------------------------------------------------
# Defensive substring scan over Stage 30.2 production source
# ---------------------------------------------------------------------------


_FORBIDDEN_SOURCE_CANONICAL_SUBSTRINGS: tuple = (
    "h" + "ttps://discord.com",
    "h" + "ttps://discordapp.com",
    "h" + "ttps://api.birdeye.so",
    "h" + "ttps://api.helius",
    "h" + "ttps://api.dexscreener",
    "h" + "ttps://chainstack.com",
    "/api/webhooks/",
    "Phoenix_Bot",
    "phoenix_bot",
)


def test_stage30_2_modules_carry_no_canonical_forbidden_substring() -> None:
    for module_path in _stage30_2_production_module_paths():
        text = module_path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_SOURCE_CANONICAL_SUBSTRINGS:
            assert needle not in text, (
                f"{module_path.name} carries forbidden canonical "
                f"substring: {needle}"
            )
