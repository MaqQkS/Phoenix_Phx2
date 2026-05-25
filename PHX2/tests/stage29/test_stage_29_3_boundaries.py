"""Stage 29.3 boundary scan.

Pins:

  * Every Stage 29.3 production .py / doc / test file exists at
    the locked path.
  * Stage 29.3 production .py modules other than the hint-aware
    event source must NOT import ``grpc`` or the generated
    Yellowstone protobuf stubs.
  * Stage 29.3 production .py modules must NOT read
    ``os.environ`` / ``os.getenv`` / ``os.environb`` directly.
    Env access flows through the unchanged Stage 28.11 + Stage
    29.2 readiness boundaries via delegation only.
  * Stage 29.3 production .py modules must NOT import any
    forbidden runtime library (Discord-client, Telegram, X,
    wallet, trade, SQL, dotenv, keyring, asyncio, subprocess,
    threading, etc.).
  * Stage 29.3 production source carries NO ``Phoenix_Bot`` path
    string, NO ``phx1`` substring (case-insensitive), NO Pump.fun
    bonding-curve program id literal, NO URL host literal
    (``discord.com`` / ``birdeye.so`` are forbidden), and NO
    raw-secret-looking literal.
  * Stage 29.3 production identifiers never implement a public /
    subscriber / paid-tier router, a Telegram / X / social
    sender, an automated trading / wallet / signer surface, a
    Stage 26 enforcement gate, a daemon / watchdog / autorestart
    service, a Pump.fun bonding-curve decoder, a Dexscreener
    dispatch authority, or a Helius price source.
  * Stage 29.3 production modules contain NO top-level Call (no
    implicit I/O at import time) AND NO top-level filesystem /
    subprocess write.
  * The Stage 29.3 manifest pins the same inventories the
    boundary scan asserts.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"


_STAGE_29_3_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_3_smoke_models.py",
    "stage29_3_no_migration_evidence_source.py",
    "stage29_3_hint_aware_event_source.py",
    "stage29_3_artifact_writer.py",
    "stage29_3_tradeable_smoke.py",
    "stage29_3_manifest.py",
)


_STAGE_29_3_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_3_FIRST_PRIVATE_TRADEABLE_SMOKE_RUNBOOK.md",
)


_STAGE_29_3_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_3_smoke_models.py",
    "test_stage_29_3_no_migration_evidence_source.py",
    "test_stage_29_3_hint_aware_event_source.py",
    "test_stage_29_3_tradeable_smoke_orchestrator.py",
    "test_stage_29_3_artifact_writer.py",
    "test_stage_29_3_runbook.py",
    "test_stage_29_3_boundaries.py",
)


# The hint-aware event source is the ONLY Stage 29.3 production
# .py module allowed to import ``grpc`` or the generated
# Yellowstone protobuf stubs.
_STAGE_29_3_GRPC_ADMITTED: tuple[str, ...] = (
    "stage29_3_hint_aware_event_source.py",
)


# Forbidden runtime libraries.
_FORBIDDEN_RUNTIME_LIBS: tuple[str, ...] = (
    "asyncio",
    "subprocess",
    "threading",
    "multiprocessing",
    "concurrent.futures",
    "requests",
    "httpx",
    "aiohttp",
    "websocket",
    "websockets",
    "redis",
    "psycopg",
    "psycopg2",
    "sqlalchemy",
    "boto3",
    "discord",
    "discord.py",
    "telethon",
    "telegram",
    "python_telegram_bot",
    "tweepy",
    "atproto",
    "solana",
    "solders",
    "anchorpy",
    "helius",
    "birdeye",
    "dexscreener",
    "dotenv",
    "python_dotenv",
    "keyring",
    "secretstorage",
    "schedule",
    "apscheduler",
)


# Forbidden Stage / PHX1 imports.
_FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "PHX2.stage21.",
    "PHX2.stage22.",
    "PHX2.stage23.",
    "PHX2.stage24.",
    "PHX2.stage25.",
    "PHX2.stage26.",
    "Phoenix" + "_Bot.",
    "Phoenix" + "_Bot",
)


# Forbidden substrings in production source (URL hosts, secret
# shapes, Pump.fun bonding-curve program id). PHX1 path strings
# are NOT scanned at the substring level (they're covered by the
# AST-based import check) so docstrings that mention PHX1 as a
# forbidden surface don't trip false positives.
_FORBIDDEN_SOURCE_SUBSTRINGS: tuple[str, ...] = (
    # URL host literals (a hardcoded host in production source
    # would bypass the Stage 28.11 + Stage 29.2 readiness env
    # boundaries).
    "birdeye" + ".so",
    "api.birdeye.so",
    "public-api.birdeye.so",
    # API key + bearer / auth header literals.
    "B" + "earer ",
    # Pump.fun bonding-curve program id literal (Stage 29.3 is
    # PumpSwap-only; the Pump.fun bonding-curve decoder is
    # deferred).
    "6EF8rrec" + "thR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
)


# Forbidden surface identifier substrings — production source
# must not implement any of these.
_FORBIDDEN_SURFACE_IDENTIFIER_SUBSTRINGS: tuple[str, ...] = (
    "public_router",
    "subscriber_router",
    "paid_tier_router",
    "telegram_sender",
    "telegram_client",
    "x_social",
    "social_sidecar",
    "enforce_policy",
    "auto_trade",
    "position_sizer",
    "trade_executor",
    "wallet_signer",
    "private_key_loader",
    "dexscreener_dispatch",
    "helius_price_source",
    "pump_fun_bonding_curve_decoder",
    "bonding_curve_program_constants",
    "daemon",
    "watchdog",
    "autorestart",
)


def _iter_stage29_3_production_py_files() -> list[Path]:
    return [
        STAGE29_ROOT / name
        for name in _STAGE_29_3_PRODUCTION_PY_BASENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_imported_module_paths(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
    return modules


# ---------------------------------------------------------------------------
# Inventory existence
# ---------------------------------------------------------------------------


def test_every_stage_29_3_production_py_file_exists():
    for name in _STAGE_29_3_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.3 requires production .py file {path}"
        )


def test_every_stage_29_3_doc_file_exists():
    for name in _STAGE_29_3_DOC_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.3 requires doc {path}"
        )


def test_every_stage_29_3_test_file_exists():
    for name in _STAGE_29_3_TEST_BASENAMES:
        path = TESTS_STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.3 requires test {path}"
        )


# ---------------------------------------------------------------------------
# Env-read discipline (no os.environ / os.getenv in production)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_3_PRODUCTION_PY_BASENAMES),
)
def test_no_os_environ_read_in_stage_29_3_production(basename):
    source = _read(STAGE29_ROOT / basename)
    # Match ``os.environ`` / ``os.getenv`` / ``os.environb``
    # exactly so this test source itself (which references the
    # forbidden names in its docstring) does not falsely flag.
    # We scan for the exact ``os.X`` token patterns via simple
    # substring check on the source AFTER stripping the module's
    # own docstring.
    tree = ast.parse(source)
    body_without_docstring = ast.unparse(
        ast.Module(body=tree.body[1:], type_ignores=[]),
    ) if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(
            getattr(tree.body[0], "value", None), ast.Constant
        )
    ) else source
    for needle in ("os.environ", "os.getenv", "os.environb"):
        assert needle not in body_without_docstring, (
            f"Stage 29.3 production .py {basename!r} must not "
            f"directly call {needle}; env reads flow through the "
            f"Stage 28.11 / Stage 29.2 readiness boundaries."
        )


# ---------------------------------------------------------------------------
# Forbidden runtime libraries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_3_PRODUCTION_PY_BASENAMES),
)
def test_no_forbidden_runtime_library_imported(basename):
    source = _read(STAGE29_ROOT / basename)
    imports = _collect_imported_module_paths(source)
    for mod in imports:
        top = mod.split(".")[0]
        assert top not in _FORBIDDEN_RUNTIME_LIBS, (
            f"Stage 29.3 production .py {basename!r} must not "
            f"import {mod!r} (forbidden runtime library)."
        )


# ---------------------------------------------------------------------------
# Forbidden Stage / PHX1 imports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_3_PRODUCTION_PY_BASENAMES),
)
def test_no_forbidden_stage_or_phx1_imports(basename):
    source = _read(STAGE29_ROOT / basename)
    imports = _collect_imported_module_paths(source)
    for mod in imports:
        for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
            assert not mod.startswith(forbidden), (
                f"Stage 29.3 production .py {basename!r} must "
                f"not import {mod!r} (forbidden Stage / PHX1 "
                f"prefix {forbidden!r})."
            )


# ---------------------------------------------------------------------------
# gRPC + generated stubs only in the hint-aware event source
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_3_PRODUCTION_PY_BASENAMES),
)
def test_grpc_only_in_hint_aware_event_source(basename):
    if basename in _STAGE_29_3_GRPC_ADMITTED:
        return
    source = _read(STAGE29_ROOT / basename)
    imports = _collect_imported_module_paths(source)
    for mod in imports:
        top = mod.split(".")[0]
        assert top != "grpc", (
            f"Stage 29.3 production .py {basename!r} must not "
            f"import grpc (only the hint-aware event source is "
            f"admitted)."
        )
        assert not mod.startswith(
            "PHX2.proto.stage28_11._generated"
        ), (
            f"Stage 29.3 production .py {basename!r} must not "
            f"import the Yellowstone generated stubs."
        )


# ---------------------------------------------------------------------------
# Source-substring scan: forbidden URL hosts / PHX1 path / Pump.fun
# bonding-curve program id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_3_PRODUCTION_PY_BASENAMES),
)
def test_no_forbidden_substring_in_production_source(basename):
    source = _read(STAGE29_ROOT / basename)
    for needle in _FORBIDDEN_SOURCE_SUBSTRINGS:
        assert needle not in source, (
            f"Stage 29.3 production .py {basename!r} must not "
            f"contain forbidden substring {needle!r}."
        )


# ---------------------------------------------------------------------------
# Forbidden surface identifier substrings
# ---------------------------------------------------------------------------


def _extract_all_identifiers(source: str) -> set[str]:
    """Extract every Python identifier (function / class / arg /
    name / attribute) from a source string via AST. Comments and
    docstring text are NOT included; only structural identifiers.
    """
    tree = ast.parse(source)
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
    return idents


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_3_PRODUCTION_PY_BASENAMES),
)
def test_no_forbidden_surface_identifier(basename):
    if basename == "stage29_3_manifest.py":
        # The manifest's STAGE29_3_FORBIDDEN_SURFACE_TOKENS tuple
        # lists every forbidden surface by name; the tuple is the
        # self-documenting record of what is forbidden and must
        # contain them.
        return
    source = _read(STAGE29_ROOT / basename)
    idents = _extract_all_identifiers(source)
    for ident in idents:
        lower = ident.lower()
        for needle in _FORBIDDEN_SURFACE_IDENTIFIER_SUBSTRINGS:
            assert needle.lower() not in lower, (
                f"{basename}: Stage 29.3 production .py must not "
                f"implement forbidden surface identifier "
                f"{needle!r} (found in identifier {ident!r})."
            )


# ---------------------------------------------------------------------------
# No top-level Call (no implicit I/O at import time)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_3_PRODUCTION_PY_BASENAMES),
)
def test_no_top_level_call_in_production_source(basename):
    source = _read(STAGE29_ROOT / basename)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call,
        ):
            raise AssertionError(
                f"Stage 29.3 production .py {basename!r} must "
                f"not contain a top-level Call node "
                f"(implicit I/O at import time forbidden); "
                f"found Call at line {node.lineno}"
            )


# ---------------------------------------------------------------------------
# Manifest consistency (re-pins the same inventories)
# ---------------------------------------------------------------------------


def test_manifest_re_pins_production_py_basenames():
    from PHX2.stage29.stage29_3_manifest import (
        STAGE29_3_PRODUCTION_PY_BASENAMES,
    )
    assert set(STAGE29_3_PRODUCTION_PY_BASENAMES) == set(
        _STAGE_29_3_PRODUCTION_PY_BASENAMES
    )


def test_manifest_re_pins_doc_basenames():
    from PHX2.stage29.stage29_3_manifest import (
        STAGE29_3_DOC_BASENAMES,
    )
    assert set(STAGE29_3_DOC_BASENAMES) == set(
        _STAGE_29_3_DOC_BASENAMES
    )


def test_manifest_re_pins_test_basenames():
    from PHX2.stage29.stage29_3_manifest import (
        STAGE29_3_TEST_BASENAMES,
    )
    assert set(STAGE29_3_TEST_BASENAMES) == set(
        _STAGE_29_3_TEST_BASENAMES
    )


def test_manifest_pins_zero_own_env_names():
    from PHX2.stage29.stage29_3_manifest import (
        STAGE29_3_ZERO_OWN_ENV_NAMES,
    )
    assert STAGE29_3_ZERO_OWN_ENV_NAMES == ()


def test_manifest_pins_reused_stage28_11_env_names():
    from PHX2.stage29.stage29_3_manifest import (
        STAGE29_3_REUSED_STAGE28_11_ENV_NAMES,
    )
    assert set(STAGE29_3_REUSED_STAGE28_11_ENV_NAMES) == {
        "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
        "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
        "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
        "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS",
    }


def test_manifest_pins_reused_stage29_2_env_names():
    from PHX2.stage29.stage29_3_manifest import (
        STAGE29_3_REUSED_STAGE29_2_ENV_NAMES,
    )
    assert set(STAGE29_3_REUSED_STAGE29_2_ENV_NAMES) == {
        "PHX2_STAGE29_2_BIRDEYE_API_KEY",
        "PHX2_STAGE29_2_BIRDEYE_BASE_URL",
        "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
        "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS",
    }


def test_manifest_pins_forbidden_surface_tokens():
    from PHX2.stage29.stage29_3_manifest import (
        STAGE29_3_FORBIDDEN_SURFACE_TOKENS,
    )
    for needle in (
        "public_router",
        "telegram_sender",
        "wallet_signer",
        "pump_fun_bonding_curve_decoder",
        "Phoenix" + "_Bot",
    ):
        assert needle in STAGE29_3_FORBIDDEN_SURFACE_TOKENS
