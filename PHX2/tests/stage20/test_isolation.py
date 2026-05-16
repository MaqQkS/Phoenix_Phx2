"""Stage 20.2 import-isolation guards (Phase D).

AST-based scan over every ``.py`` file under ``PHX2/stage20/`` and
``PHX2/tests/stage20/``. Walks every ``Import`` / ``ImportFrom``
node and asserts none of them resolve to a forbidden module path.

Forbidden modules come from Hard Constraints #3 and #4:

  Stage 17/18/19 production code (any submodule):
    PHX2.stage17, PHX2.stage18, PHX2.stage19

  Network / external clients:
    requests, httpx, aiohttp, urllib3

  Chat / messaging:
    discord, discord.py, slack_sdk, telegram

  Trading-provider clients:
    helius, birdeye, dexscreener, jupiter, pump

  Local subprocess / sockets / DB / streaming:
    sqlite3, subprocess, socket, grpc, grpcio, websockets

Stage 20 is observe-only, offline, file-based. None of the above
are legitimately importable from within Stage 20 or its tests.
"""

from __future__ import annotations

import ast
import pathlib


_FORBIDDEN_MODULES: frozenset[str] = frozenset({
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "discord",
    "discord.py",
    "slack_sdk",
    "telegram",
    "helius",
    "birdeye",
    "dexscreener",
    "jupiter",
    "pump",
    "sqlite3",
    "subprocess",
    "socket",
    "grpc",
    "grpcio",
    "websockets",
})


_ROOTS: tuple[pathlib.Path, ...] = (
    pathlib.Path("PHX2/stage20"),
    pathlib.Path("PHX2/tests/stage20"),
)


def _is_forbidden(module_path: str) -> bool:
    """Return True if ``module_path`` is or is a submodule of any
    forbidden module.
    """

    if not module_path:
        return False
    for forbidden in _FORBIDDEN_MODULES:
        if module_path == forbidden or module_path.startswith(forbidden + "."):
            return True
    return False


def _all_python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in _ROOTS:
        files.extend(sorted(root.rglob("*.py")))
    return files


def _collect_import_violations() -> list[tuple[str, int, str]]:
    """Walk every .py file under the locked roots and collect any
    forbidden ``Import`` or ``ImportFrom`` node.

    Returns a list of ``(file, lineno, module)`` tuples.
    """

    violations: list[tuple[str, int, str]] = []
    for f in _all_python_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden(alias.name):
                        violations.append((str(f), node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if _is_forbidden(mod):
                    violations.append((str(f), node.lineno, mod))
    return violations


def test_no_forbidden_imports_anywhere_under_stage20():
    violations = _collect_import_violations()
    assert violations == [], (
        "Forbidden imports detected:\n"
        + "\n".join(f"  {f}:{ln} -> {mod}" for f, ln, mod in violations)
    )


def test_isolation_scan_covers_expected_file_count():
    """Sanity guard: assert the AST scan actually walked > 0 files.

    Catches a regression where the roots were mistyped or moved
    and the scan silently scans nothing.
    """

    files = _all_python_files()
    assert len(files) > 0
    # At a minimum we should see the locked Stage 20.2 modules.
    names = {f.name for f in files}
    for required in (
        "builder.py",
        "artifact_writers.py",
        "manifest_assembler.py",
        "runner.py",
        "ids.py",
        "constants.py",
        "input_validators.py",
    ):
        assert required in names, f"isolation scan missed {required}"


def test_no_stage17_or_stage18_or_stage19_imports_specifically():
    """Targeted check for the upstream PHX2 stage imports -- the
    most common regression vector.
    """

    violations = _collect_import_violations()
    upstream_hits = [
        v for v in violations
        if v[2].startswith(("PHX2.stage17", "PHX2.stage18", "PHX2.stage19"))
    ]
    assert upstream_hits == []
