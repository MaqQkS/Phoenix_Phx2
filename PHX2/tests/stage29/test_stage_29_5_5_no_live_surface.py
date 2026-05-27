"""Stage 29.5.5 no-live-surface pins.

Pins that Stage 29.5.5 production source carries:

  * NO outbound HTTP / WebSocket / socket / gRPC import.
  * NO Discord / Telegram / X / social / webhook client
    import.
  * NO Helius / Chainstack / Birdeye / Pump.fun / Dexscreener
    runtime library import.
  * NO ``asyncio`` / ``threading`` / ``multiprocessing`` /
    ``subprocess`` / ``signal`` import (Stage 29.5.5 is a
    pure / synchronous offline composition).
  * NO env-read site.
  * NO Discord HTTP transport import (Stage 28.4 audited
    transport, etc.).
  * NO Stage 28.9 live provider session import.

The boundary scan in test_stage_29_5_5_boundaries.py also
covers some of these; this file pins the no-live-surface
intent at a dedicated test boundary so a future refactor that
silently widens the allowed-import set trips a clear failure
here.
"""

from __future__ import annotations

import ast
from pathlib import Path


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"


_STAGE_29_5_5_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_5_render_models.py",
    "stage29_5_5_private_discord_migration_context_renderer.py",
    "stage29_5_5_migration_context_recorder.py",
    "stage29_5_5_side_channel_artifact_writer.py",
    "stage29_5_5_manifest.py",
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


_FORBIDDEN_LIVE_IMPORT_PATTERNS: tuple[str, ...] = (
    # Outbound network primitives
    "urllib",
    "urllib.request",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "websocket",
    "http.client",
    "socket",
    "grpc",
    # Async / scheduling / signal-based control flow
    "asyncio",
    "threading",
    "multiprocessing",
    "subprocess",
    "signal",
    "sched",
    "queue",
    # Outbound message clients
    "discord",
    "telegram",
    "telethon",
    "tweepy",
    "twitter",
    # External provider / DEX libraries
    "solders",
    "solana",
    "helius",
    "jupiter",
    "dexscreener",
    "construct",
    "base58",
    # Persistence / scheduling / secrets
    "sqlite3",
    "sqlalchemy",
    "dotenv",
    "keyring",
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
)


def test_no_stage_29_5_5_production_imports_live_surface() -> None:
    for name in _STAGE_29_5_5_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        source = _read(path)
        targets = _collect_imported_module_paths(source)
        for target in targets:
            if target.startswith("PHX2."):
                continue
            lower = target.lower()
            for pattern in (
                _FORBIDDEN_LIVE_IMPORT_PATTERNS
            ):
                assert (
                    lower != pattern
                    and not lower.startswith(pattern + ".")
                ), (
                    f"{name}: Stage 29.5.5 must not import "
                    f"live-surface module {target!r} "
                    f"(matched forbidden pattern "
                    f"{pattern!r})"
                )


_FORBIDDEN_PHX2_LIVE_MODULES: tuple[str, ...] = (
    # Stage 28.4 audited HTTP transport (Discord)
    "PHX2.stage28.audited_http_transport",
    "PHX2.stage28.audited_http_transport_models",
    # Stage 28.9 live provider session
    "PHX2.stage28.live_provider_session_adapter",
    "PHX2.stage28.live_provider_session_models",
    "PHX2.stage28.live_provider_session_transport",
    # Stage 28.11 Chainstack live
    "PHX2.stage28.chainstack_yellowstone_grpc_models",
    "PHX2.stage28.chainstack_yellowstone_grpc_readiness",
    # Stage 29.2 Birdeye live
    "PHX2.stage29.stage29_2_birdeye_http_transport",
    "PHX2.stage29.stage29_2_birdeye_price_source",
    "PHX2.stage29.stage29_2_birdeye_ath_source",
    # Stage 29.3 live hint source
    "PHX2.stage29.stage29_3_hint_aware_event_source",
)


def test_no_stage_29_5_5_production_imports_phx2_live_modules() -> None:
    for name in _STAGE_29_5_5_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert (
                target not in _FORBIDDEN_PHX2_LIVE_MODULES
            ), (
                f"{name}: Stage 29.5.5 must not import "
                f"live-surface PHX2 module {target!r}"
            )


def test_no_stage_29_5_5_production_reads_env() -> None:
    """Cross-check the env-read isolation pin at this file's
    boundary too.
    """
    env_attr_names = frozenset(
        {"environ", "getenv", "environb"}
    )
    leaked: list[str] = []
    for name in _STAGE_29_5_5_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        source = _read(path)
        tree = ast.parse(source)
        os_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        os_aliases.add(
                            alias.asname or alias.name,
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module == "os":
                    for alias in node.names:
                        if alias.name in env_attr_names:
                            leaked.append(name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id in os_aliases
                    and node.attr in env_attr_names
                ):
                    leaked.append(name)
    assert not leaked, (
        f"Stage 29.5.5 production must not read os.environ; "
        f"offenders: {leaked!r}"
    )
