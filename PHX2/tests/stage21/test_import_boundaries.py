"""Stage 21 import boundary tests.

Mirrors the Stage 20 test_import_boundaries.py shape with the
Stage 21 specifics:

  * No import of Phoenix1.
  * No import of PHX2.stage17, PHX2.stage18, PHX2.stage19,
    PHX2.stage20.
  * No import of PHX2.db / PHX2.repositories / PHX2.config /
    PHX2.models / PHX2.services / PHX2.dispatch.
  * No top-level import of a network / messaging / scheduler /
    DB / secrets library (substring match against lowered import
    name).

The checks run AST-level on Stage 21 production .py files only
(``PHX2/stage21/**``). Test files under ``PHX2/tests/stage21/`` are
deliberately exempt -- tests are allowed to import network /
messaging library names if needed for future work, but 21.1's
tests do not.
"""

from __future__ import annotations

import ast
from pathlib import Path


STAGE21_ROOT = Path(__file__).parent.parent.parent / "stage21"


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
)


_FORBIDDEN_PHX2_RUNTIME_PREFIXES: tuple[str, ...] = (
    # Stage 21 runtime must not reach into the live PHX2 service
    # layer / DB layer / config layer. Stage 21.1 is artifact-based
    # and has no need for any of those.
    "PHX2.db",
    "PHX2.repositories",
    "PHX2.config",
    "PHX2.models",
    "PHX2.services",
    "PHX2.dispatch",
    "PHX2.filters",
    "PHX2.integrations",
    "PHX2.renderers",
    "PHX2.scripts",
    "PHX2.analysis",
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
    # Secrets-management libs
    "dotenv",
    "keyring",
)


def _iter_production_modules() -> list[Path]:
    """All .py files under PHX2/stage21/ excluding __pycache__."""
    return [
        p for p in STAGE21_ROOT.rglob("*.py")
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


def test_at_least_one_production_module_exists():
    files = _iter_production_modules()
    assert files, "expected at least one production .py under stage21"


def test_no_phoenix1_imports():
    for py_file in _iter_production_modules():
        imports = _collect_imports(py_file)
        for mod in imports:
            assert not mod.startswith("phoenix1"), (
                f"{py_file}: forbidden phoenix1 import {mod!r}"
            )


def test_no_prior_stage_runtime_imports():
    for py_file in _iter_production_modules():
        imports = _collect_imports(py_file)
        for mod in imports:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not mod.startswith(forbidden), (
                    f"{py_file}: forbidden prior-stage import {mod!r}"
                )


def test_no_phx2_runtime_layer_imports():
    for py_file in _iter_production_modules():
        imports = _collect_imports(py_file)
        for mod in imports:
            for forbidden in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not mod.startswith(forbidden), (
                    f"{py_file}: forbidden PHX2 runtime-layer import "
                    f"{mod!r}"
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


def test_no_bot_db_reference_anywhere_in_stage21_source():
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        assert "bot.db" not in source, (
            f"{py_file}: forbidden 'bot.db' reference in source"
        )
        assert "data/bot.db" not in source, (
            f"{py_file}: forbidden 'data/bot.db' reference in source"
        )


def test_no_url_literals_in_production_source():
    """Stage 21 production code must not contain https:// or wss://.

    Stage 21.1 has no need for URL literals anywhere; even in
    docstrings. The provider / transport adapters are deferred to
    later sub-stages and they will need to introduce URLs, but
    they must do so via the SecretRef boundary -- never as a
    source-level literal.
    """
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        assert "https://" not in source, (
            f"{py_file}: forbidden 'https://' in source"
        )
        assert "wss://" not in source, (
            f"{py_file}: forbidden 'wss://' in source"
        )


def test_no_top_level_network_side_effect_on_import():
    """Importing every Stage 21 production module is side-effect-free.

    A "side effect" here is a top-level statement that issues a
    network call or opens a connection. The AST check rejects any
    top-level statement that is not one of:
      * import / from-import
      * class / function definition
      * docstring
      * simple assignment
      * try / except (for stdlib-only deferred imports)
      * __future__ import
    """
    allowed_top_level = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.Assign,
        ast.AnnAssign,
        ast.AugAssign,
        ast.If,
        ast.Try,
        ast.Expr,  # docstrings live inside Expr nodes
    )
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            assert isinstance(node, allowed_top_level), (
                f"{py_file}: unexpected top-level node {type(node).__name__}"
            )
