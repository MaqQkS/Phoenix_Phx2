"""Stage 30.1 tier decision models tests.

Pure read-only tests over the Stage 30.1 closed-set vocabularies,
the immutable record shape, the forbidden-field-name guard, the
error class, the locked schema version, and the locked artifact
basename. The tests also AST-scan every Stage 30.1 production
module to confirm there is no forbidden import (no env / socket /
network / cross-stage production import).

Discipline: no env reads, no network, no Discord, no provider
calls. Stdlib + pytest only.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from PHX2.stage30 import tier_decision_models as M


# ---------------------------------------------------------------------------
# Locked schema version + basename pins
# ---------------------------------------------------------------------------


def test_minor_version_byte_pinned() -> None:
    assert M.STAGE30_1_MINOR_VERSION == "30.1"


def test_schema_version_byte_pinned() -> None:
    assert (
        M.STAGE30_1_TIER_DECISION_SCHEMA_VERSION
        == "stage30_1_v0_tier_decision"
    )


def test_artifact_basename_byte_pinned() -> None:
    assert (
        M.STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
        == "stage30_1_tier_decisions.jsonl"
    )


# ---------------------------------------------------------------------------
# Tier tokens
# ---------------------------------------------------------------------------


def test_tier_token_values_exact_set() -> None:
    assert M.TIER_TOKEN_VALUES == (
        "Tier 1",
        "Tier 2",
        "Tier 3",
        "Tier Unknown",
        "Tier Not Applicable",
    )


def test_tier_token_values_no_duplicates() -> None:
    assert len(M.TIER_TOKEN_VALUES) == len(set(M.TIER_TOKEN_VALUES))


def test_tier_token_values_all_non_empty_str() -> None:
    for value in M.TIER_TOKEN_VALUES:
        assert isinstance(value, str)
        assert value != ""


def test_is_tier_token_value_accepts_each_member() -> None:
    for value in M.TIER_TOKEN_VALUES:
        assert M.is_tier_token_value(value)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "tier 1",
        "T1",
        "T-1",
        "Tier1",
        "TIER 1",
        "Tier 4",
        None,
        0,
        0.0,
        [],
        (),
        {},
        object(),
    ],
)
def test_is_tier_token_value_rejects_non_members(bad: object) -> None:
    assert not M.is_tier_token_value(bad)


# ---------------------------------------------------------------------------
# Tier reasons
# ---------------------------------------------------------------------------


def test_tier_reason_values_no_duplicates() -> None:
    assert len(M.TIER_REASON_VALUES) == len(set(M.TIER_REASON_VALUES))


def test_tier_reason_values_all_non_empty_str() -> None:
    for value in M.TIER_REASON_VALUES:
        assert isinstance(value, str)
        assert value != ""


_EXPECTED_TIER_REASON_TOKENS: tuple[str, ...] = (
    "NA_MIGRATION_MISSING",
    "NA_MIGRATION_UNTRUSTED",
    "NA_MIGRATION_UNSUPPORTED_PAIR",
    "NA_MIGRATION_SOURCE_ERROR",
    "NA_ATH_MAY_INCLUDE_PRE_MIGRATION",
    "UNKNOWN_ATH_NOT_PRESENT",
    "UNKNOWN_DRAWDOWN_MISSING",
    "UNKNOWN_DRAWDOWN_MALFORMED",
    "UNKNOWN_BELOW_TIER_1",
    "UNKNOWN_IN_GAP_T1_T2",
    "UNKNOWN_IN_GAP_T2_T3",
    "UNKNOWN_GRAVEYARD",
    "TIER_1_IN_BAND",
    "TIER_2_IN_BAND",
    "TIER_3_IN_BAND",
)


def test_tier_reason_values_exact_set() -> None:
    assert set(M.TIER_REASON_VALUES) == set(
        _EXPECTED_TIER_REASON_TOKENS
    )


def test_tier_reason_constants_match_values() -> None:
    mapping = {
        M.TIER_REASON_NA_MIGRATION_MISSING: "NA_MIGRATION_MISSING",
        M.TIER_REASON_NA_MIGRATION_UNTRUSTED: (
            "NA_MIGRATION_UNTRUSTED"
        ),
        M.TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR: (
            "NA_MIGRATION_UNSUPPORTED_PAIR"
        ),
        M.TIER_REASON_NA_MIGRATION_SOURCE_ERROR: (
            "NA_MIGRATION_SOURCE_ERROR"
        ),
        M.TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION: (
            "NA_ATH_MAY_INCLUDE_PRE_MIGRATION"
        ),
        M.TIER_REASON_UNKNOWN_ATH_NOT_PRESENT: (
            "UNKNOWN_ATH_NOT_PRESENT"
        ),
        M.TIER_REASON_UNKNOWN_DRAWDOWN_MISSING: (
            "UNKNOWN_DRAWDOWN_MISSING"
        ),
        M.TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED: (
            "UNKNOWN_DRAWDOWN_MALFORMED"
        ),
        M.TIER_REASON_UNKNOWN_BELOW_TIER_1: "UNKNOWN_BELOW_TIER_1",
        M.TIER_REASON_UNKNOWN_IN_GAP_T1_T2: "UNKNOWN_IN_GAP_T1_T2",
        M.TIER_REASON_UNKNOWN_IN_GAP_T2_T3: "UNKNOWN_IN_GAP_T2_T3",
        M.TIER_REASON_UNKNOWN_GRAVEYARD: "UNKNOWN_GRAVEYARD",
        M.TIER_REASON_TIER_1_IN_BAND: "TIER_1_IN_BAND",
        M.TIER_REASON_TIER_2_IN_BAND: "TIER_2_IN_BAND",
        M.TIER_REASON_TIER_3_IN_BAND: "TIER_3_IN_BAND",
    }
    for constant_value, expected_text in mapping.items():
        assert constant_value == expected_text


def test_is_tier_reason_value_accepts_each_member() -> None:
    for value in M.TIER_REASON_VALUES:
        assert M.is_tier_reason_value(value)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "TIER_4_IN_BAND",
        "tier_1_in_band",
        "NA_MIGRATION_INVALID",
        "NA_MIGRATION_CONFLICTING",
        None,
        0,
        [],
        object(),
    ],
)
def test_is_tier_reason_value_rejects_non_members(bad: object) -> None:
    assert not M.is_tier_reason_value(bad)


# ---------------------------------------------------------------------------
# Basis tokens
# ---------------------------------------------------------------------------


def test_basis_values_exact_set() -> None:
    assert M.BASIS_VALUES == ("price-basis", "mc-basis")


def test_basis_constants_match_values() -> None:
    assert M.BASIS_PRICE == "price-basis"
    assert M.BASIS_MC == "mc-basis"


def test_is_basis_value_accepts_each_member() -> None:
    for value in M.BASIS_VALUES:
        assert M.is_basis_value(value)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "PRICE-BASIS",
        "Price-Basis",
        "mc_basis",
        "basis-unknown",
        "unknown",
        None,
        0,
        [],
        object(),
    ],
)
def test_is_basis_value_rejects_non_members(bad: object) -> None:
    assert not M.is_basis_value(bad)


# ---------------------------------------------------------------------------
# TierDecisionRecord
# ---------------------------------------------------------------------------


_EXPECTED_RECORD_FIELDS: tuple[str, ...] = (
    "schema_version",
    "session_id",
    "ping_id",
    "candidate_id",
    "mint",
    "basis",
    "drawdown_from_ath_raw",
    "drop_positive",
    "ath_status",
    "ath_since_migration_status",
    "migration_status",
    "tier_token",
    "tier_reason",
    "created_at_utc",
)


def test_tier_decision_record_fields_exact() -> None:
    assert M.TierDecisionRecord._fields == _EXPECTED_RECORD_FIELDS


def test_tier_decision_record_has_no_forbidden_field_names() -> None:
    for name in M.TierDecisionRecord._fields:
        assert not M.is_forbidden_record_field_name(name), name


def test_tier_decision_record_construction_minimal() -> None:
    rec = M.TierDecisionRecord(
        schema_version=M.STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
        session_id=None,
        ping_id=None,
        candidate_id=None,
        mint=None,
        basis=M.BASIS_PRICE,
        drawdown_from_ath_raw=None,
        drop_positive=None,
        ath_status="PRESENT",
        ath_since_migration_status="POST_MIGRATION_ONLY",
        migration_status="PRESENT",
        tier_token=M.TIER_TOKEN_TIER_UNKNOWN,
        tier_reason=M.TIER_REASON_UNKNOWN_DRAWDOWN_MISSING,
        created_at_utc="2026-05-27T12:00:00Z",
    )
    assert rec.tier_token == "Tier Unknown"
    assert rec.tier_reason == "UNKNOWN_DRAWDOWN_MISSING"
    assert rec.basis == "price-basis"


def test_tier_decision_record_is_namedtuple_immutable() -> None:
    rec = M.TierDecisionRecord(
        schema_version=M.STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
        session_id=None,
        ping_id=None,
        candidate_id=None,
        mint=None,
        basis=M.BASIS_PRICE,
        drawdown_from_ath_raw=None,
        drop_positive=None,
        ath_status="PRESENT",
        ath_since_migration_status="POST_MIGRATION_ONLY",
        migration_status="PRESENT",
        tier_token=M.TIER_TOKEN_TIER_1,
        tier_reason=M.TIER_REASON_TIER_1_IN_BAND,
        created_at_utc="2026-05-27T12:00:00Z",
    )
    with pytest.raises(AttributeError):
        rec.tier_token = "Tier 2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FORBIDDEN_RECORD_FIELD_NAMES
# ---------------------------------------------------------------------------


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
    list(_EXPECTED_RECORD_FIELDS),
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
# Stage30_1TierDecisionError
# ---------------------------------------------------------------------------


def test_error_is_exception_subclass() -> None:
    assert issubclass(M.Stage30_1TierDecisionError, Exception)


def test_error_carries_reason_attribute() -> None:
    err = M.Stage30_1TierDecisionError("MY_REASON")
    assert err.reason == "MY_REASON"
    assert "MY_REASON" in str(err)


# ---------------------------------------------------------------------------
# Forbidden-imports AST scan over every Stage 30 production module
# ---------------------------------------------------------------------------


_FORBIDDEN_TOP_LEVEL_IMPORTS: tuple[str, ...] = (
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
)


_FORBIDDEN_NAME_SUBSTRINGS: tuple[str, ...] = (
    "Phoenix_Bot",
    "phoenix_bot",
)


_FORBIDDEN_PHX2_PACKAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
    "PHX2.stage25",
    "PHX2.stage26",
    "PHX2.stage28",
    "PHX2.stage29",
)


def _stage30_production_module_paths() -> list[Path]:
    stage30_root = (
        Path(__file__).resolve().parent.parent.parent / "stage30"
    )
    return sorted(
        p
        for p in stage30_root.glob("*.py")
        if p.name != "__init__.py"
    )


def _module_import_names(module_path: Path) -> list[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.append(node.module)
    return imports


def test_stage30_production_modules_have_no_forbidden_top_level_imports() -> (
    None
):
    paths = _stage30_production_module_paths()
    assert paths, "expected at least one Stage 30 production module"
    for module_path in paths:
        imports = _module_import_names(module_path)
        for imported in imports:
            top = imported.split(".")[0]
            assert top not in _FORBIDDEN_TOP_LEVEL_IMPORTS, (
                f"{module_path.name} imports forbidden top-level "
                f"module: {imported}"
            )


def test_stage30_production_modules_dont_carry_legacy_name_substrings() -> (
    None
):
    paths = _stage30_production_module_paths()
    for module_path in paths:
        text = module_path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_NAME_SUBSTRINGS:
            assert needle not in text, (
                f"{module_path.name} carries forbidden name "
                f"substring: {needle}"
            )


def test_stage30_production_modules_dont_import_other_phx2_stages() -> (
    None
):
    paths = _stage30_production_module_paths()
    for module_path in paths:
        imports = _module_import_names(module_path)
        for imported in imports:
            for prefix in _FORBIDDEN_PHX2_PACKAGE_PREFIXES:
                assert not imported.startswith(prefix), (
                    f"{module_path.name} imports forbidden "
                    f"Stage package: {imported}"
                )


def test_stage30_production_modules_only_phx2_dep_is_stage27_or_stage30() -> (
    None
):
    paths = _stage30_production_module_paths()
    for module_path in paths:
        imports = _module_import_names(module_path)
        for imported in imports:
            if imported.startswith("PHX2"):
                assert imported.startswith(
                    "PHX2.stage27."
                ) or imported.startswith("PHX2.stage30."), (
                    f"{module_path.name} imports unexpected PHX2 "
                    f"module: {imported}"
                )
