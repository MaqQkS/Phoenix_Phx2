"""Static purity checks on renderer source files.

These tests guard the architectural boundary: the pure renderer and adapters
must not call clocks or import repositories. They are static (file-content
scans), so they catch accidental drift even before runtime tests do.
"""

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
RENDERER_PATH = REPO_ROOT / "PHX2" / "renderers" / "alert_renderer.py"
PLAIN_TEXT_PATH = REPO_ROOT / "PHX2" / "renderers" / "adapters" / "plain_text.py"
DISCORD_ADAPTER_PATH = REPO_ROOT / "PHX2" / "renderers" / "adapters" / "discord.py"

PURE_FILES = [RENDERER_PATH, PLAIN_TEXT_PATH, DISCORD_ADAPTER_PATH]

FORBIDDEN_CALL_FRAGMENTS = (
    "datetime.now",
    "datetime.utcnow",
    "time.time",
    "time.monotonic",
)

FORBIDDEN_IMPORT_PREFIXES = (
    "PHX2.db",
    "PHX2.db.repositories",
    "PHX2.db.connection",
    "PHX2.db.migrations",
    "PHX2.services",
    "PHX2.integrations",
)


@pytest.mark.parametrize("source_file", PURE_FILES, ids=lambda p: p.name)
def test_no_clock_calls_in_pure_file(source_file: Path):
    """Pure files must not contain any forbidden clock-call fragments."""

    contents = source_file.read_text(encoding="utf-8")
    for fragment in FORBIDDEN_CALL_FRAGMENTS:
        assert fragment not in contents, (
            f"{source_file.name} contains forbidden call fragment "
            f"'{fragment}'."
        )


@pytest.mark.parametrize("source_file", PURE_FILES, ids=lambda p: p.name)
def test_no_repository_or_service_imports(source_file: Path):
    """Pure files must not import from repository, db, or service modules."""

    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                for prefix in FORBIDDEN_IMPORT_PREFIXES:
                    assert not module_name.startswith(prefix), (
                        f"{source_file.name} imports forbidden module "
                        f"'{module_name}'."
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            for prefix in FORBIDDEN_IMPORT_PREFIXES:
                assert not node.module.startswith(prefix), (
                    f"{source_file.name} imports forbidden module "
                    f"'{node.module}'."
                )


def test_renderer_module_tree_does_not_import_repositories_except_assembler():
    """Only RenderingContextAssembler is allowed to import repositories.

    Walks every .py file in PHX2/renderers/ and asserts that none — except
    context.py (which contains RenderingContextAssembler) — import from
    PHX2.db.repositories.
    """

    renderers_root = REPO_ROOT / "PHX2" / "renderers"
    allowed = {renderers_root / "context.py"}
    for path in renderers_root.rglob("*.py"):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert not node.module.startswith("PHX2.db.repositories"), (
                    f"{path.relative_to(REPO_ROOT)} imports repositories — "
                    f"only RenderingContextAssembler is allowed to do that."
                )


def test_no_dispatch_event_writes_in_renderer_tree():
    """Stage 8A must not write dispatch_events anywhere in the renderer tree."""

    renderers_root = REPO_ROOT / "PHX2" / "renderers"
    for path in renderers_root.rglob("*.py"):
        contents = path.read_text(encoding="utf-8")
        assert "dispatch_events" not in contents, (
            f"{path.relative_to(REPO_ROOT)} mentions dispatch_events; that "
            "belongs in 8B, not 8A."
        )


def test_no_network_imports_in_renderer_tree():
    """Renderers must not import network or HTTP libraries."""

    renderers_root = REPO_ROOT / "PHX2" / "renderers"
    forbidden_network_modules = {
        "requests",
        "urllib",
        "urllib.request",
        "http.client",
        "aiohttp",
        "httpx",
    }
    for path in renderers_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_network_modules, (
                        f"{path.relative_to(REPO_ROOT)} imports forbidden "
                        f"network module '{alias.name}'."
                    )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                assert module_name not in forbidden_network_modules, (
                    f"{path.relative_to(REPO_ROOT)} imports forbidden "
                    f"network module '{module_name}'."
                )
