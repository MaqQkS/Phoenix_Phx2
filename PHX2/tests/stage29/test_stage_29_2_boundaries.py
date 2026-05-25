"""Stage 29.2 boundary scan.

Pins:

  * Every Stage 29.2 production .py / doc / test file exists at
    the locked path.
  * Stage 29.2 production .py modules other than the readiness
    module must NOT read ``os.environ`` / ``os.getenv`` /
    ``os.environb``.
  * Stage 29.2 production .py modules other than the http
    transport module must NOT import ``urllib.request`` /
    ``urllib.parse`` / ``urllib.error`` / ``requests`` / ``httpx``
    / ``aiohttp``.
  * Stage 29.2 production .py modules must NOT import any Stage
    21-26 module, any Stage 27 module beyond the Stage 27.4
    Protocol surface, any Stage 28.0 - 28.9 dispatch surface, or
    any Stage 28.10 / 28.11 surface beyond what Stage 29.2 needs
    (currently nothing).
  * Stage 29.2 production .py modules must NOT import any
    forbidden runtime library (Discord / Telegram / X / wallet /
    trade / SQL / dotenv / keyring / etc.).
  * Stage 29.2 production source carries NO ``Phoenix_Bot`` path
    string, NO ``phx1`` substring (case-insensitive), NO Pump.fun
    bonding-curve program id literal, NO URL host literal
    (``birdeye.so`` is forbidden), and NO raw-secret-looking
    literal.
  * Stage 29.2 production identifiers never implement a Stage
    29.3 surface, a Pump.fun bonding-curve decoder, a public /
    subscriber / paid-tier router, a Telegram / X / social
    sender, an automated trading / wallet / signer surface, a
    Stage 26 enforcement gate, or a daemon / watchdog /
    autorestart service.
  * Stage 29.2 production modules contain NO top-level Call (no
    implicit I/O at import time) AND NO top-level filesystem /
    subprocess write.
  * The Stage 29.2 manifest pins the same inventories the
    boundary scan asserts.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"


_STAGE_29_2_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "birdeye_constants.py",
    "stage29_2_birdeye_models.py",
    "stage29_2_birdeye_readiness.py",
    "stage29_2_birdeye_http_transport.py",
    "stage29_2_birdeye_price_source.py",
    "stage29_2_birdeye_ath_source.py",
    "stage29_2_birdeye_probe_models.py",
    "stage29_2_birdeye_probe.py",
    "stage29_2_manifest.py",
)


_STAGE_29_2_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_2_BIRDEYE_PRICE_ATH_RUNBOOK.md",
)


_STAGE_29_2_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_2_birdeye_constants.py",
    "test_stage_29_2_birdeye_models.py",
    "test_stage_29_2_birdeye_readiness.py",
    "test_stage_29_2_birdeye_http_transport.py",
    "test_stage_29_2_birdeye_price_source.py",
    "test_stage_29_2_birdeye_ath_source.py",
    "test_stage_29_2_birdeye_probe_models.py",
    "test_stage_29_2_birdeye_probe.py",
    "test_stage_29_2_runbook.py",
    "test_stage_29_2_boundaries.py",
)


_STAGE_29_2_ENV_READ_ADMITTED: tuple[str, ...] = (
    "stage29_2_birdeye_readiness.py",
)


_STAGE_29_2_HTTP_ADMITTED: tuple[str, ...] = (
    "stage29_2_birdeye_http_transport.py",
)


def _iter_stage29_2_production_py_files() -> list[Path]:
    return [
        STAGE29_ROOT / name
        for name in _STAGE_29_2_PRODUCTION_PY_BASENAMES
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
# 1. Inventory existence
# ---------------------------------------------------------------------------


def test_every_stage_29_2_production_py_file_exists():
    for name in _STAGE_29_2_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.2 requires production .py file {path}"
        )


def test_every_stage_29_2_doc_file_exists():
    for name in _STAGE_29_2_DOC_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.2 requires doc {path}"
        )


def test_every_stage_29_2_test_file_exists():
    for name in _STAGE_29_2_TEST_BASENAMES:
        path = TESTS_STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.2 requires test {path}"
        )


# ---------------------------------------------------------------------------
# 2. Env-read isolation
# ---------------------------------------------------------------------------


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


def _module_reads_environ(source: str) -> bool:
    tree = ast.parse(source)
    os_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    if alias.name in _ENV_ATTR_NAMES:
                        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in _ENV_ATTR_NAMES
            ):
                return True
    return False


def test_only_readiness_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage29_2_production_py_files():
        if path.name in _STAGE_29_2_ENV_READ_ADMITTED:
            continue
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 29.2 admits os.environ only in "
        f"{_STAGE_29_2_ENV_READ_ADMITTED!r}; offenders: {leaked!r}"
    )


def test_readiness_module_does_read_environ():
    src = _read(
        STAGE29_ROOT / "stage29_2_birdeye_readiness.py"
    )
    assert _module_reads_environ(src), (
        "stage29_2_birdeye_readiness.py must read os.environ "
        "(the sole Stage 29.2 env-read site)"
    )


# ---------------------------------------------------------------------------
# 3. urllib / HTTP-client admission
# ---------------------------------------------------------------------------


_HTTP_IMPORT_PATTERNS: tuple[str, ...] = (
    "urllib",
    "urllib.request",
    "urllib.parse",
    "urllib.error",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "http.client",
)


def _module_imports_any(
    source: str, needles: tuple[str, ...]
) -> set[str]:
    targets = _collect_imported_module_paths(source)
    hits: set[str] = set()
    for t in targets:
        for n in needles:
            if t == n or t.startswith(n + "."):
                hits.add(t)
    return hits


def test_only_http_transport_imports_urllib():
    for path in _iter_stage29_2_production_py_files():
        if path.name in _STAGE_29_2_HTTP_ADMITTED:
            continue
        hits = _module_imports_any(
            _read(path), _HTTP_IMPORT_PATTERNS
        )
        assert not hits, (
            f"{path.name}: Stage 29.2 admits HTTP imports only "
            f"in {_STAGE_29_2_HTTP_ADMITTED!r}; offenders: "
            f"{sorted(hits)!r}"
        )


def test_http_transport_imports_urllib():
    src = _read(
        STAGE29_ROOT / "stage29_2_birdeye_http_transport.py"
    )
    targets = _collect_imported_module_paths(src)
    assert any(
        t.startswith("urllib") for t in targets
    ), (
        "stage29_2_birdeye_http_transport.py must import urllib "
        "(the sole Stage 29.2 HTTP transport)"
    )


# ---------------------------------------------------------------------------
# 4. No forbidden prior-stage / dispatch surface imports
# ---------------------------------------------------------------------------


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
    "PHX2.stage25",
    "PHX2.stage26",
)


def test_no_stage_29_2_production_imports_prior_stages():
    for path in _iter_stage29_2_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden prior-stage "
                    f"import {target!r}"
                )


# Stage 27 imports admitted by Stage 29.2 -- ONLY the Stage 27.4
# Protocol surface (price/ATH context contracts + reader +
# models). Every other Stage 27 import is forbidden.
_STAGE_27_ADMITTED_SIBLING_PREFIXES: tuple[str, ...] = (
    "PHX2.stage27.price_ath_context_contracts",
    "PHX2.stage27.price_ath_context_models",
    "PHX2.stage27.price_ath_context_reader",
)


def test_stage_29_2_production_only_imports_authorized_stage_27():
    for path in _iter_stage29_2_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if not target.startswith("PHX2.stage27"):
                continue
            ok = any(
                target == prefix
                or target.startswith(prefix + ".")
                for prefix in (
                    _STAGE_27_ADMITTED_SIBLING_PREFIXES
                )
            )
            assert ok, (
                f"{path.name}: stage27 import {target!r} is "
                f"not in the Stage 29.2 admitted prefix list"
            )


_FORBIDDEN_STAGE_28_IMPORTS: tuple[str, ...] = (
    "PHX2.stage28.live_provider_session_adapter",
    "PHX2.stage28.live_provider_session_transport",
    "PHX2.stage28.live_provider_session_models",
    "PHX2.stage28.bounded_private_session_runner",
    "PHX2.stage28.audited_http_transport",
    "PHX2.stage28.dispatch_ledger",
    "PHX2.stage28.heartbeat_writer",
    "PHX2.stage28.health_snapshot_writer",
    "PHX2.stage28.failure_classification",
    "PHX2.stage28.retry_policy",
    "PHX2.stage28.chainstack_yellowstone_event_source",
    "PHX2.stage28.chainstack_yellowstone_candidate_assembler",
    "PHX2.stage28.chainstack_yellowstone_contracts",
    "PHX2.stage28.chainstack_yellowstone_grpc_client",
    "PHX2.stage28.chainstack_yellowstone_grpc_probe",
    "PHX2.stage28.chainstack_yellowstone_grpc_readiness",
    "PHX2.stage28.chainstack_yellowstone_grpc_decode",
    "PHX2.stage28.chainstack_yellowstone_grpc_models",
    "PHX2.stage28.chainstack_yellowstone_models",
)


def test_no_stage_29_2_production_imports_stage_28():
    for path in _iter_stage29_2_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert (
                target not in _FORBIDDEN_STAGE_28_IMPORTS
            ), (
                f"{path.name}: Stage 29.2 must not import "
                f"Stage 28 surface {target!r}"
            )


# ---------------------------------------------------------------------------
# 5. Forbidden runtime libraries
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "solders",
    "solana",
    "construct",
    "base58",
    "helius",
    "jupiter",
    "discord",
    "telegram",
    "telethon",
    "webhook_client",
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "sqlalchemy",
    "sqlite3",
    "dotenv",
    "keyring",
    "tweepy",
    "twitter",
    "socket",
    "asyncio",
    "threading",
    "multiprocessing",
    "subprocess",
    "queue",
    "sched",
    "dexscreener",
)


def test_no_stage_29_2_production_imports_forbidden_runtime():
    for path in _iter_stage29_2_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if target.startswith("PHX2."):
                continue
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path.name}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
                )


# ---------------------------------------------------------------------------
# 6. PHX1 / Pump.fun bonding-curve / URL host / raw-secret scan
# ---------------------------------------------------------------------------


def test_no_stage_29_2_production_imports_phx1():
    for path in _iter_stage29_2_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            assert "phoenix_bot" not in lower, (
                f"{path.name}: forbidden PHX1 import path "
                f"{target!r}"
            )
            assert "phx1" not in lower, (
                f"{path.name}: forbidden PHX1 substring in "
                f"import path {target!r}"
            )


def test_no_stage_29_2_production_source_carries_phx1_path():
    for path in _iter_stage29_2_production_py_files():
        source = _read(path)
        lower = source.lower()
        assert "phoenix_bot" not in lower, (
            f"{path.name}: forbidden 'Phoenix_Bot' substring"
        )


def test_no_stage_29_2_production_carries_pump_fun_program_id():
    for path in _iter_stage29_2_production_py_files():
        source = _read(path)
        assert (
            "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
            not in source
        ), (
            f"{path.name}: forbidden Pump.fun bonding-curve "
            f"program id literal"
        )


_FORBIDDEN_URL_HOSTS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "public-api.birdeye" + ".so",
    "pro-api.birdeye" + ".so",
    "business-api.birdeye" + ".so",
    "birdeye" + ".so",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com",
    "yellowstone" + ".chainstack",
    "dexscreener" + ".com",
)


def test_no_url_host_literal_in_stage_29_2_production_source():
    for path in _iter_stage29_2_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOSTS:
            assert needle not in source, (
                f"{path.name}: forbidden URL host literal "
                f"{needle!r}"
            )


_FORBIDDEN_RAW_SECRET_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "BIRDEYE_API" + "_KEY=",
    "CHAINSTACK_API" + "_KEY=",
)


def test_no_raw_secret_literal_in_stage_29_2_production_source():
    for path in _iter_stage29_2_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
            assert needle not in source, (
                f"{path.name}: forbidden raw-secret-looking "
                f"literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# 7. Forbidden later-substage / public-routing identifier scan
# ---------------------------------------------------------------------------


_FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS: tuple[
    str, ...
] = (
    "public" + "_router",
    "subscriber" + "_router",
    "paid" + "_tier_router",
    "telegram" + "_sender",
    "telegram" + "_client",
    "x" + "_social",
    "social" + "_sidecar",
    "tweet" + "_ranking",
    "enforcement" + "_gate",
    "enforce" + "_policy",
    "approval" + "_gate",
    "approval" + "_status",
    "auto" + "_trade",
    "position" + "_size",
    "trade" + "_executor",
    "wallet" + "_signer",
    "private" + "_key_loader",
    "buy" + "_signal",
    "sell" + "_signal",
    "execute" + "_trade",
    "control" + "_server",
    "http" + "_control_server",
    "auto" + "restart",
    "systemd" + "_unit",
    "dexscreener" + "_dispatch",
    "helius" + "_price",
    "tradeable" + "_smoke_harness",
    "bonding" + "_curve_decoder",
    "stage29_3" + "_",
    "stage_29_3" + "_",
)


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


def test_no_stage_29_2_production_identifier_implements_forbidden_surface():
    for path in _iter_stage29_2_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{path.name}: forbidden later-substage / "
                    f"public-routing identifier substring "
                    f"{needle!r} in identifier {ident!r}"
                )


# ---------------------------------------------------------------------------
# 8. No top-level Call / filesystem-write
# ---------------------------------------------------------------------------


def _has_top_level_call(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            return True
    return False


def test_no_stage_29_2_production_has_top_level_call():
    for path in _iter_stage29_2_production_py_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path.name}: Stage 29.2 production must not "
            f"contain top-level Call (no implicit I/O at "
            f"import time)"
        )


_FORBIDDEN_TOP_LEVEL_WRITE_TARGETS: frozenset[str] = frozenset(
    {
        "write_bytes",
        "write_text",
        "open",
        "mkdir",
        "touch",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "system",
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
    }
)


def test_no_stage_29_2_production_has_top_level_write():
    for path in _iter_stage29_2_production_py_files():
        tree = ast.parse(_read(path))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(
                node.value, ast.Call
            ):
                func = node.value.func
                if isinstance(func, ast.Attribute):
                    assert (
                        func.attr
                        not in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                    )
                elif isinstance(func, ast.Name):
                    assert (
                        func.id
                        not in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                    )


# ---------------------------------------------------------------------------
# 9. Manifest pin sanity
# ---------------------------------------------------------------------------


def test_manifest_pins_production_inventory():
    from PHX2.stage29.stage29_2_manifest import (
        STAGE29_2_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_2_PRODUCTION_PY_BASENAMES
        == _STAGE_29_2_PRODUCTION_PY_BASENAMES
    )


def test_manifest_pins_doc_inventory():
    from PHX2.stage29.stage29_2_manifest import (
        STAGE29_2_DOC_BASENAMES,
    )
    assert STAGE29_2_DOC_BASENAMES == _STAGE_29_2_DOC_BASENAMES


def test_manifest_pins_test_inventory():
    from PHX2.stage29.stage29_2_manifest import (
        STAGE29_2_TEST_BASENAMES,
    )
    assert (
        STAGE29_2_TEST_BASENAMES == _STAGE_29_2_TEST_BASENAMES
    )


def test_manifest_pins_env_read_admission():
    from PHX2.stage29.stage29_2_manifest import (
        STAGE29_2_ENV_READ_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_2_ENV_READ_ADMITTED_BASENAMES
        == _STAGE_29_2_ENV_READ_ADMITTED
    )


def test_manifest_pins_http_admission():
    from PHX2.stage29.stage29_2_manifest import (
        STAGE29_2_HTTP_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_2_HTTP_ADMITTED_BASENAMES
        == _STAGE_29_2_HTTP_ADMITTED
    )


def test_manifest_lists_forbidden_surfaces():
    from PHX2.stage29.stage29_2_manifest import (
        STAGE29_2_FORBIDDEN_SURFACES,
    )
    required = {
        "Discord send",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / private-key / signer logic",
        "Pump.fun bonding-curve decoder",
        "Stage 29.3 tradeable Discord smoke",
        "PHX1 import path",
        "Stage 26 policy enforcement activation",
        "public routing",
        "subscriber routing",
        "paid tier routing",
        "Dexscreener as a price fallback in Stage 29.2",
        "Helius as a price source",
    }
    assert required.issubset(set(STAGE29_2_FORBIDDEN_SURFACES))


def test_manifest_pins_env_names_match_readiness():
    from PHX2.stage29.stage29_2_manifest import (
        STAGE29_2_READ_ENV_NAMES_PIN,
    )
    from PHX2.stage29.stage29_2_birdeye_readiness import (
        STAGE29_2_READ_ENV_NAMES,
    )
    assert (
        STAGE29_2_READ_ENV_NAMES_PIN == STAGE29_2_READ_ENV_NAMES
    )


# ---------------------------------------------------------------------------
# 10. Stage 28 / Stage 29.1 sibling import sanity
# ---------------------------------------------------------------------------


_STAGE_29_1_ADMITTED_SIBLING_PREFIXES: tuple[str, ...] = (
    "PHX2.stage29.stage29_1_manifest",
)


def test_no_stage_29_2_imports_stage_29_1_internals():
    """Stage 29.2 may re-use the Stage 29.1 manifest (for
    re-exports like ``WRAPPED_SOL_MINT``) but must NOT reach
    into Stage 29.1's internal hint-extractor surfaces.
    """
    for path in _iter_stage29_2_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if not target.startswith("PHX2.stage29."):
                continue
            # Stage 29.2's own modules are fine.
            if target.startswith(
                "PHX2.stage29.stage29_2_"
            ):
                continue
            if target == "PHX2.stage29.birdeye_constants":
                continue
            # Stage 29.1 sibling: allow only the manifest.
            ok = any(
                target == prefix
                or target.startswith(prefix + ".")
                for prefix in (
                    _STAGE_29_1_ADMITTED_SIBLING_PREFIXES
                )
            )
            assert ok, (
                f"{path.name}: stage29 sibling import "
                f"{target!r} is not in the Stage 29.2 "
                f"admitted prefix list"
            )
