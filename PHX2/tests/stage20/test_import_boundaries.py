"""Stage 20 import boundary tests.

Stage 20 production modules must NOT import PHX2.stage17,
PHX2.stage18, or PHX2.stage19. Schema constants from those
stages are hand-duplicated in PHX2/stage20/constants.py per the
locked import-boundary policy (matching the Stage 18 / Stage 19
convention enforced by their own test_import_boundaries.py).

The forbidden-imports list also covers network, messaging,
scheduler, DB, and provider client libraries -- none of which
Stage 20 production code should ever need.

These tests run AST-level checks rather than substring matches
on the source so module names that happen to contain a banned
substring (e.g. ``"discord"`` inside an unrelated comment) do
not trip the check; only actual imports do.
"""

from __future__ import annotations

import ast
from pathlib import Path


STAGE20_ROOT = Path(__file__).parent.parent.parent / "stage20"


_FORBIDDEN_UPSTREAM_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
)

_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    # Network / RPC
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    # Provider clients (substring match against lowered import name)
    "helius",
    "birdeye",
    "dexscreener",
    "jupiter",
    "jito",
    # Messaging
    "discord",
    "telegram",
    "telethon",
    "webhook",
    # Scheduler / daemon
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "daemon",
    # DB
    "sqlalchemy",
    "sqlite3",
    # Secrets
    "dotenv",
    "keyring",
)


def _iter_production_modules() -> list[Path]:
    """All .py files under PHX2/stage20/ excluding __pycache__."""
    return [
        p for p in STAGE20_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _collect_imports(file_path: Path) -> set[str]:
    """Return the set of imported module names declared in file_path."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def test_no_upstream_stage_imports():
    production_files = _iter_production_modules()
    assert production_files, "expected at least one production .py under stage20"
    for py_file in production_files:
        imports = _collect_imports(py_file)
        for mod in imports:
            for forbidden in _FORBIDDEN_UPSTREAM_STAGE_PREFIXES:
                assert not mod.startswith(forbidden), (
                    f"{py_file}: forbidden upstream import {mod!r}"
                )


def test_no_forbidden_runtime_modules():
    for py_file in _iter_production_modules():
        imports = _collect_imports(py_file)
        for mod in imports:
            lower = mod.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{py_file}: forbidden module pattern {pattern!r} "
                    f"in import {mod!r}"
                )


def test_no_db_or_repositories_imports():
    for py_file in _iter_production_modules():
        imports = _collect_imports(py_file)
        for mod in imports:
            assert not mod.startswith("PHX2.repositories"), (
                f"{py_file}: forbidden import {mod!r}"
            )
            assert not mod.startswith("PHX2.db"), (
                f"{py_file}: forbidden import {mod!r}"
            )


def test_no_url_literals_in_production_source():
    """Stage 20 production code must not contain https:// or wss:// strings.

    Stage 20 has no need for URL literals anywhere (even in
    docstrings); this is a stricter version of the prompt's
    "outside docstring URL references" rule because the
    minimal-needs of the validator surface guarantee no URL is
    legitimately required.
    """
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        assert "https://" not in source, (
            f"{py_file}: forbidden 'https://' in source"
        )
        assert "wss://" not in source, (
            f"{py_file}: forbidden 'wss://' in source"
        )
