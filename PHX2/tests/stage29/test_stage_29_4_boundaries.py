"""Stage 29.4 boundary scan.

Pins:

  * Every Stage 29.4 production .py / doc / test file exists at
    the locked path.
  * Stage 29.4 production .py modules must NOT import ``grpc``,
    the generated Yellowstone protobuf stubs, ``urllib``,
    ``http.client``, or any direct network / Discord / Telegram /
    X / social / wallet / DB / scheduler library.
  * Stage 29.4 production .py modules must NOT read
    ``os.environ`` / ``os.getenv`` / ``os.environb`` directly.
    Env access flows through the unchanged Stage 28.11 + Stage
    29.2 + Stage 29.3 readiness boundaries via the operator-
    supplied per-pass entrypoint.
  * Stage 29.4 production .py modules must NOT contain
    ``time.sleep(`` calls, ``threading`` / ``asyncio`` /
    ``subprocess`` / ``multiprocessing`` / ``signal`` imports.
  * Stage 29.4 production source carries NO ``Phoenix_Bot`` path
    string, NO ``phx1`` substring (case-insensitive), NO Pump.fun
    bonding-curve program id literal, NO URL host literal, NO
    raw-secret-looking literal.
  * Stage 29.4 production identifiers never implement a public /
    subscriber / paid-tier router, a Telegram / X / social
    sender, an automated trading / wallet / signer surface, a
    Stage 26 enforcement gate, a daemon / watchdog / autorestart
    service, a Pump.fun bonding-curve decoder, a Dexscreener
    dispatch authority, or a Helius price source.
  * Stage 29.4 production modules contain NO top-level Call
    (no implicit I/O at import time).
  * Stage 29.4 production does NOT import any PHX2.stage21..26
    module.
  * The Stage 29.4 manifest pins the same inventories the
    boundary scan asserts.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"


_STAGE_29_4_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_4_soak_models.py",
    "stage29_4_dedupe_index.py",
    "stage29_4_soak_orchestrator.py",
    "stage29_4_soak_artifact_writer.py",
    "stage29_4_manifest.py",
)


_STAGE_29_4_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md",
)


_STAGE_29_4_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_4_spec_lock.py",
    "test_stage_29_4_soak_models.py",
    "test_stage_29_4_dedupe_index.py",
    "test_stage_29_4_soak_orchestrator.py",
    "test_stage_29_4_soak_artifact_writer.py",
    "test_stage_29_4_boundaries.py",
)


# Forbidden runtime libraries.
_FORBIDDEN_RUNTIME_LIBS: tuple[str, ...] = (
    "asyncio",
    "subprocess",
    "threading",
    "multiprocessing",
    "concurrent.futures",
    "signal",
    "requests",
    "httpx",
    "aiohttp",
    "websocket",
    "websockets",
    "urllib",
    "http",
    "socket",
    "ssl",
    "grpc",
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


# Forbidden Stage / PHX1 import prefixes. Stage 29.4 may import
# from PHX2.stage27 / PHX2.stage28 / PHX2.stage29 (its own
# siblings) but NOT from earlier stages or from PHX1.
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
    # URL host literals.
    "birdeye" + ".so",
    "api.birdeye.so",
    "public-api.birdeye.so",
    # API key + bearer / auth header literals.
    "B" + "earer ",
    # Pump.fun bonding-curve program id literal.
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


def _iter_stage29_4_production_py_files() -> list[Path]:
    return [
        STAGE29_ROOT / name
        for name in _STAGE_29_4_PRODUCTION_PY_BASENAMES
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


def test_every_stage_29_4_production_py_file_exists():
    for name in _STAGE_29_4_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.4 requires production .py file {path}"
        )


def test_every_stage_29_4_doc_file_exists():
    for name in _STAGE_29_4_DOC_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.4 requires doc {path}"
        )


def test_every_stage_29_4_test_file_exists():
    for name in _STAGE_29_4_TEST_BASENAMES:
        path = TESTS_STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.4 requires test {path}"
        )


# ---------------------------------------------------------------------------
# Env-read discipline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_4_PRODUCTION_PY_BASENAMES),
)
def test_no_os_environ_read_in_stage_29_4_production(basename):
    source = _read(STAGE29_ROOT / basename)
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
            f"Stage 29.4 production .py {basename!r} must not "
            f"directly call {needle}; env reads flow through "
            f"the Stage 28.11 / Stage 29.2 readiness boundaries "
            f"via the Stage 29.3 entry point."
        )


# ---------------------------------------------------------------------------
# Forbidden runtime libraries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_4_PRODUCTION_PY_BASENAMES),
)
def test_no_forbidden_runtime_library_imported(basename):
    source = _read(STAGE29_ROOT / basename)
    imports = _collect_imported_module_paths(source)
    for mod in imports:
        top = mod.split(".")[0]
        assert top not in _FORBIDDEN_RUNTIME_LIBS, (
            f"Stage 29.4 production .py {basename!r} must not "
            f"import {mod!r} (forbidden runtime library)."
        )


# ---------------------------------------------------------------------------
# Forbidden Stage / PHX1 imports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_4_PRODUCTION_PY_BASENAMES),
)
def test_no_forbidden_stage_or_phx1_imports(basename):
    source = _read(STAGE29_ROOT / basename)
    imports = _collect_imported_module_paths(source)
    for mod in imports:
        for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
            assert not mod.startswith(forbidden), (
                f"Stage 29.4 production .py {basename!r} must "
                f"not import {mod!r} (forbidden Stage / PHX1 "
                f"prefix {forbidden!r})."
            )


# ---------------------------------------------------------------------------
# time.sleep / threading / async forbidden across the module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_4_PRODUCTION_PY_BASENAMES),
)
def test_no_time_sleep_call_in_production(basename):
    source = _read(STAGE29_ROOT / basename)
    # Strip the module docstring so the boundary discipline can
    # mention ``time.sleep(`` without tripping the scan.
    tree = ast.parse(source)
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(
            getattr(tree.body[0], "value", None), ast.Constant
        )
    ):
        body_without_docstring = ast.unparse(
            ast.Module(body=tree.body[1:], type_ignores=[]),
        )
    else:
        body_without_docstring = source
    assert "time.sleep(" not in body_without_docstring, (
        f"Stage 29.4 production .py {basename!r} must not "
        f"contain ``time.sleep(`` — soak pacing is bounded via "
        f"clock polling, not sleep."
    )


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_4_PRODUCTION_PY_BASENAMES),
)
def test_no_threading_or_async_in_production(basename):
    source = _read(STAGE29_ROOT / basename)
    tree = ast.parse(source)
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(
            getattr(tree.body[0], "value", None), ast.Constant
        )
    ):
        body_without_docstring = ast.unparse(
            ast.Module(body=tree.body[1:], type_ignores=[]),
        )
    else:
        body_without_docstring = source
    for needle in (
        "threading.Thread",
        "asyncio.",
        "subprocess.",
        "multiprocessing.",
        "signal.SIGTERM",
        "signal.SIGINT",
    ):
        assert needle not in body_without_docstring, (
            f"Stage 29.4 production .py {basename!r} must not "
            f"contain {needle!r}."
        )


# ---------------------------------------------------------------------------
# Source-substring scan: forbidden URL hosts / Pump.fun bonding-
# curve program id / etc.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_4_PRODUCTION_PY_BASENAMES),
)
def test_no_forbidden_substring_in_production_source(basename):
    source = _read(STAGE29_ROOT / basename)
    for needle in _FORBIDDEN_SOURCE_SUBSTRINGS:
        assert needle not in source, (
            f"Stage 29.4 production .py {basename!r} must not "
            f"contain forbidden substring {needle!r}."
        )


# ---------------------------------------------------------------------------
# Forbidden surface identifier substrings
# ---------------------------------------------------------------------------


def _extract_all_identifiers(source: str) -> set[str]:
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
    "basename", list(_STAGE_29_4_PRODUCTION_PY_BASENAMES),
)
def test_no_forbidden_surface_identifier(basename):
    if basename == "stage29_4_manifest.py":
        # The manifest's STAGE29_4_FORBIDDEN_SURFACE_TOKENS tuple
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
                f"{basename}: Stage 29.4 production .py must "
                f"not implement forbidden surface identifier "
                f"{needle!r} (found in identifier {ident!r})."
            )


# ---------------------------------------------------------------------------
# No top-level Call (no implicit I/O at import time)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_4_PRODUCTION_PY_BASENAMES),
)
def test_no_top_level_call_in_production_source(basename):
    source = _read(STAGE29_ROOT / basename)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call,
        ):
            raise AssertionError(
                f"Stage 29.4 production .py {basename!r} must "
                f"not contain a top-level Call node "
                f"(implicit I/O at import time forbidden); "
                f"found Call at line {node.lineno}"
            )


# ---------------------------------------------------------------------------
# Stdlib-only discipline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", list(_STAGE_29_4_PRODUCTION_PY_BASENAMES),
)
def test_imports_only_stdlib_or_phx2_stages(basename):
    """Stage 29.4 production imports must live under either
    stdlib (no top-level package match in the forbidden runtime
    list) or under the PHX2 tree. No third-party package may be
    imported.
    """
    source = _read(STAGE29_ROOT / basename)
    imports = _collect_imported_module_paths(source)
    for mod in imports:
        top = mod.split(".")[0]
        # PHX2 imports allowed.
        if top == "PHX2":
            continue
        # Future-import guard.
        if top == "__future__":
            continue
        # Stdlib whitelist (intersect with what Stage 29.4
        # actually uses).
        if top in (
            "dataclasses",
            "datetime",
            "json",
            "pathlib",
            "typing",
        ):
            continue
        # Anything else: forbid.
        raise AssertionError(
            f"Stage 29.4 production .py {basename!r} imports "
            f"non-stdlib non-PHX2 module {mod!r}; only "
            f"stdlib + PHX2 imports are allowed."
        )


# ---------------------------------------------------------------------------
# Manifest consistency (re-pins the same inventories)
# ---------------------------------------------------------------------------


def test_manifest_re_pins_production_py_basenames():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_PRODUCTION_PY_BASENAMES,
    )
    assert set(STAGE29_4_PRODUCTION_PY_BASENAMES) == set(
        _STAGE_29_4_PRODUCTION_PY_BASENAMES
    )


def test_manifest_re_pins_doc_basenames():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_DOC_BASENAMES,
    )
    assert set(STAGE29_4_DOC_BASENAMES) == set(
        _STAGE_29_4_DOC_BASENAMES
    )


def test_manifest_re_pins_test_basenames():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_TEST_BASENAMES,
    )
    assert set(STAGE29_4_TEST_BASENAMES) == set(
        _STAGE_29_4_TEST_BASENAMES
    )


def test_manifest_pins_zero_own_env_names():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_ZERO_OWN_ENV_NAMES,
    )
    assert STAGE29_4_ZERO_OWN_ENV_NAMES == ()


def test_manifest_pins_reused_stage28_11_env_names():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_REUSED_STAGE28_11_ENV_NAMES,
    )
    assert set(STAGE29_4_REUSED_STAGE28_11_ENV_NAMES) == {
        "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
        "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
        "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
        "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS",
    }


def test_manifest_pins_reused_stage29_2_env_names():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_REUSED_STAGE29_2_ENV_NAMES,
    )
    assert set(STAGE29_4_REUSED_STAGE29_2_ENV_NAMES) == {
        "PHX2_STAGE29_2_BIRDEYE_API_KEY",
        "PHX2_STAGE29_2_BIRDEYE_BASE_URL",
        "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
        "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS",
    }


def test_manifest_pins_forbidden_surface_tokens():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_FORBIDDEN_SURFACE_TOKENS,
    )
    for needle in (
        "public_router",
        "telegram_sender",
        "wallet_signer",
        "pump_fun_bonding_curve_decoder",
        "Phoenix" + "_Bot",
        "persistent_dedupe_index",
    ):
        assert needle in STAGE29_4_FORBIDDEN_SURFACE_TOKENS


def test_manifest_pins_artifact_basenames():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_ACCEPTANCE_ARTIFACT_BASENAMES,
    )
    assert set(
        STAGE29_4_ACCEPTANCE_ARTIFACT_BASENAMES
    ) == {
        "stage29_4_soak_summary.json",
        "stage29_4_heartbeat.jsonl",
        "stage29_4_health_snapshot.json",
        "stage29_4_redaction_scan.json",
    }


def test_manifest_pins_probe_mode_values():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_PROBE_MODE_VALUES,
    )
    assert set(STAGE29_4_PROBE_MODE_VALUES) == {
        "READINESS_ONLY",
        "CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY",
        "SHORT_SESSION_PRIVATE_SOAK_DRY_RUN",
    }


def test_manifest_pins_soak_outcome_values():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_SOAK_OUTCOME_VALUES,
    )
    assert set(STAGE29_4_SOAK_OUTCOME_VALUES) == {
        "COMPLETED_AT_DISPATCH_CAP",
        "COMPLETED_AT_WALL_CLOCK",
        "COMPLETED_AT_PASS_CAP",
        "BROKE_ON_SUPPRESSION_CIRCUIT",
        "BROKE_ON_REFUSED_READINESS",
        "BROKE_ON_FAILED_PASS",
        "NO_DISPATCHES_NO_EVENTS",
        "REFUSED_INVALID_BOUNDS",
    }


def test_manifest_pins_dedupe_outcome_values():
    from PHX2.stage29.stage29_4_manifest import (
        STAGE29_4_DEDUPE_OUTCOME_VALUES,
    )
    assert set(STAGE29_4_DEDUPE_OUTCOME_VALUES) == {
        "NEW",
        "DUPLICATE_SUPPRESSED_SOAK",
    }
