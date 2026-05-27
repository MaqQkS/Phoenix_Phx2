"""Stage 29.5.4 no-live-surface pins.

Asserts that Stage 29.5.4 production source carries NO outbound
network import (no urllib / requests / httpx / aiohttp /
websockets / websocket / http.client / socket / grpc / asyncio)
and NO Discord / Telegram / X / social transport library import.

Also pins that Stage 29.5.4 production does NOT directly call
the Stage 27.6 candidate assembler, the Stage 28.4 audited HTTP
transport, the Stage 28.9 live provider session wrapper, the
Stage 28.11 Chainstack gRPC channel, or the Stage 29.2 Birdeye
HTTP transport. The adapter is consumed BY the Stage 27.4
``read_migration_context`` reader at the Stage 27.6 boundary;
the adapter itself opens no network connection.
"""

from __future__ import annotations

import ast
from pathlib import Path


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"


_PRODUCTION_FILES: tuple[Path, ...] = (
    STAGE29_ROOT
    / "stage29_5_4_migration_context_source_adapter.py",
    STAGE29_ROOT / "stage29_5_4_manifest.py",
)


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


_FORBIDDEN_OUTBOUND_NETWORK_IMPORTS: tuple[str, ...] = (
    "urllib",
    "urllib.request",
    "urllib.parse",
    "urllib.error",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "websocket",
    "http.client",
    "socket",
    "grpc",
    "asyncio",
)


def test_adapter_imports_no_outbound_network() -> None:
    src = _read(_PRODUCTION_FILES[0])
    imports = _collect_imported_module_paths(src)
    for imp in imports:
        for forbidden in _FORBIDDEN_OUTBOUND_NETWORK_IMPORTS:
            assert imp != forbidden and not imp.startswith(
                forbidden + "."
            ), (
                f"Stage 29.5.4 adapter imports forbidden "
                f"outbound-network module {imp!r}"
            )


def test_manifest_imports_no_outbound_network() -> None:
    src = _read(_PRODUCTION_FILES[1])
    imports = _collect_imported_module_paths(src)
    for imp in imports:
        for forbidden in _FORBIDDEN_OUTBOUND_NETWORK_IMPORTS:
            assert imp != forbidden and not imp.startswith(
                forbidden + "."
            ), (
                f"Stage 29.5.4 manifest imports forbidden "
                f"outbound-network module {imp!r}"
            )


_FORBIDDEN_TRANSPORT_OR_SOCIAL_IMPORTS: tuple[str, ...] = (
    "discord",
    "telegram",
    "telethon",
    "webhook_client",
    "tweepy",
    "twitter",
    "helius",
    "dexscreener",
    "solana",
    "solders",
)


def test_no_transport_or_social_library_import() -> None:
    for path in _PRODUCTION_FILES:
        src = _read(path)
        imports = _collect_imported_module_paths(src)
        for imp in imports:
            if imp.startswith("PHX2."):
                continue
            lower = imp.lower()
            for forbidden in (
                _FORBIDDEN_TRANSPORT_OR_SOCIAL_IMPORTS
            ):
                assert forbidden not in lower, (
                    f"{path.name}: forbidden transport / social "
                    f"library substring {forbidden!r} in import "
                    f"{imp!r}"
                )


def test_no_stage_27_assembler_import() -> None:
    """Stage 29.5.4 production must NOT import the Stage 27.6
    live candidate assembler. The adapter is consumed BY the
    assembler at runtime (via the Stage 27.4 reader), never the
    other way around.
    """
    for path in _PRODUCTION_FILES:
        src = _read(path)
        imports = _collect_imported_module_paths(src)
        for imp in imports:
            assert (
                imp
                != "PHX2.stage27.live_candidate_assembler"
            ), (
                f"{path.name}: Stage 29.5.4 must not import "
                f"the Stage 27.6 candidate assembler"
            )


def test_no_stage_28_audited_transport_import() -> None:
    for path in _PRODUCTION_FILES:
        src = _read(path)
        imports = _collect_imported_module_paths(src)
        for imp in imports:
            assert not imp.startswith("PHX2.stage28."), (
                f"{path.name}: Stage 29.5.4 must not import any "
                f"Stage 28 module; offender {imp!r}"
            )


def test_no_stage_29_2_birdeye_transport_import() -> None:
    for path in _PRODUCTION_FILES:
        src = _read(path)
        imports = _collect_imported_module_paths(src)
        for imp in imports:
            assert (
                "stage29_2_birdeye" not in imp
            ), (
                f"{path.name}: Stage 29.5.4 must not import any "
                f"Stage 29.2 Birdeye HTTP transport surface; "
                f"the operator wires Birdeye into the "
                f"ath_context_provider callable at the "
                f"adapter's constructor boundary, not via a "
                f"direct import. Offender {imp!r}"
            )


def test_no_stage_29_5_helius_ws_adapter_import() -> None:
    """Stage 29.5.4 must NOT import the Stage 29.5 Helius WS
    adapter directly. Live Helius WebSocket migration-evidence
    ingestion is deferred to Stage 29.5.6+; until then the
    operator wires evidence into the Stage 29.5.4
    evidence_provider via an in-memory list or a Stage 29.5
    artifact reader's output.
    """
    for path in _PRODUCTION_FILES:
        src = _read(path)
        imports = _collect_imported_module_paths(src)
        for imp in imports:
            assert (
                imp
                != "PHX2.stage29.stage29_5_helius_ws_adapter"
            ), (
                f"{path.name}: Stage 29.5.4 must not import "
                f"the Stage 29.5 Helius WS adapter"
            )


def test_adapter_module_has_no_top_level_socket_or_grpc_call() -> None:
    """Defense in depth: even if a future imports change opened
    a network library, the module body must not invoke any
    network-shaped call at import time. This is enforced
    holistically by the boundary scan's no-module-body-Call rule,
    but we restate the pin here so the Stage 29.5.4
    no-live-surface test surface owns it explicitly.
    """
    src = _read(_PRODUCTION_FILES[0])
    tree = ast.parse(src)
    network_shaped_attrs = (
        "connect",
        "send",
        "recv",
        "open",
        "post",
        "get",
        "put",
        "delete",
        "subscribe",
        "channel",
    )
    for stmt in tree.body:
        if isinstance(
            stmt,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            continue
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Attribute):
                if sub.attr in network_shaped_attrs:
                    raise AssertionError(
                        f"Stage 29.5.4 adapter contains "
                        f"module-body network-shaped attribute "
                        f"{sub.attr!r}"
                    )
