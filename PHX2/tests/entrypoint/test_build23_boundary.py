"""Build #23 entrypoint boundary tests.

Scans the three Build #23 launch-boundary library modules (the package marker,
the pure models leaf, the thin subprocess launcher) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``dataclasses`` /
    ``typing`` / ``json`` / ``os`` / ``subprocess`` -- the launch boundary may use
    ``os`` + ``subprocess``, but NOTHING above this owns a network / db client);
  * a positive PHX2 import allowlist (only the own sibling -- NO Stage 21-30 / PHX1
    import; the supervisor is subprocessed, never imported);
  * no network / concurrency / database module import;
  * no forbidden url / credential / host text needle and no ``://`` literal;
  * no ``shell=True`` in the subprocess launcher;
  * the single owned env pointer name is present and no credential env-var name is;
  * no implicit I/O at import time (zero top-level Call nodes).

This is the source-level complement to the behavioral launcher tests. The
entry script ``PHX2/main.py`` (which legitimately bootstraps ``sys.path`` and
parses argv) is intentionally NOT in this scanned set.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set, Tuple


ENTRYPOINT_ROOT: Path = Path(__file__).resolve().parent.parent.parent / "entrypoint"

LIBRARY_BASENAMES: Tuple[str, ...] = (
    "__init__.py",
    "launcher_models.py",
    "supervised_launcher.py",
)

ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "dataclasses",
    "typing",
    "json",
    "os",
    "subprocess",
)

FORBIDDEN_MODULES: Tuple[str, ...] = (
    "urllib",
    "socket",
    "grpc",
    "asyncio",
    "aiohttp",
    "httpx",
    "requests",
    "websockets",
    "websocket",
    "http",
    "ssl",
    "threading",
    "multiprocessing",
    "concurrent",
    "signal",
    "ftplib",
    "smtplib",
    "telnetlib",
    "dotenv",
    "keyring",
    "sqlite3",
)

# High-signal url / credential / host needles that must never appear in source.
FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
    "://",
    "discord",
    "webhook",
    "https",
    "bearer",
    "api_key",
    "chainstack",
    "helius",
)

# Credential env-var name substrings that must never appear (the launcher reads
# only the command pointer ``PHX2_SUPERVISOR_CMD``).
FORBIDDEN_CREDENTIAL_NAMES: Tuple[str, ...] = (
    "WEBHOOK",
    "DISCORD",
    "BEARER",
    "API_KEY",
    "PRIVATE_KEY",
    "WALLET",
    "SECRET",
)


def _source_of(basename: str) -> str:
    return (ENTRYPOINT_ROOT / basename).read_text(encoding="utf-8")


def _sources() -> Dict[str, str]:
    return {b: _source_of(b) for b in LIBRARY_BASENAMES}


def _imports_of(text: str) -> Set[str]:
    modules: Set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


# ---------------------------------------------------------------------------
# 1. Files exist + import cleanly
# ---------------------------------------------------------------------------


def test_library_files_exist() -> None:
    for basename in LIBRARY_BASENAMES:
        assert (ENTRYPOINT_ROOT / basename).is_file(), (
            f"Build #23 requires {basename}"
        )


def test_modules_import_cleanly() -> None:
    import PHX2.entrypoint  # noqa: F401
    import PHX2.entrypoint.launcher_models  # noqa: F401
    import PHX2.entrypoint.supervised_launcher  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Positive stdlib + PHX2 import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_imports_within_allowlist() -> None:
    for basename, text in _sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2"):
                continue
            top = module.split(".")[0]
            assert top in ALLOWED_STDLIB_IMPORTS, (
                f"{basename} imports non-allowlisted stdlib module {module!r}"
            )


def test_models_and_init_import_no_io_modules() -> None:
    # The package marker + the pure models leaf own no os / subprocess / json.
    for basename in ("__init__.py", "launcher_models.py"):
        for module in _imports_of(_source_of(basename)):
            top = module.split(".")[0]
            assert top not in ("os", "subprocess", "json"), (
                f"{basename} must not import {module!r}"
            )


def test_phx2_imports_are_only_the_own_sibling() -> None:
    for basename, text in _sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2"):
                continue
            assert module.startswith("PHX2.entrypoint"), (
                f"{basename} imports non-entrypoint PHX2 module {module!r}"
            )
            assert not module.startswith("PHX2.stage"), (
                f"{basename} imports a Stage module {module!r}; the supervisor "
                f"must be subprocessed, not imported"
            )


def test_no_forbidden_network_db_or_concurrency_imports() -> None:
    for basename, text in _sources().items():
        for module in _imports_of(text):
            top = module.split(".")[0]
            assert top not in FORBIDDEN_MODULES, (
                f"{basename} imports forbidden module {module!r}"
            )


def test_no_phx1_import() -> None:
    for basename, text in _sources().items():
        for module in _imports_of(text):
            assert not module.startswith("PHX1"), (
                f"{basename} imports PHX1 {module!r}"
            )


# ---------------------------------------------------------------------------
# 3. No url / credential / host needles; no shell=True; owned pointer only
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for basename, text in _sources().items():
        lowered = text.lower()
        for needle in FORBIDDEN_TEXT_NEEDLES:
            assert needle not in lowered, (
                f"{basename} carries forbidden text needle {needle!r}"
            )


def test_launcher_uses_no_shell_invocation() -> None:
    # AST-based: a real ``shell=True`` keyword on any call (never a docstring
    # mention of the safe behavior). The launcher must always invoke an argv list.
    tree = ast.parse(_source_of("supervised_launcher.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                assert not (
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ), "supervised_launcher must not invoke subprocess with shell=True"


def test_owned_pointer_present_no_credential_name() -> None:
    joined = "".join(_sources().values())
    assert "PHX2_SUPERVISOR_CMD" in joined
    for name in FORBIDDEN_CREDENTIAL_NAMES:
        assert name not in joined, (
            f"a credential env-var name {name!r} must never appear in the "
            f"launch boundary"
        )


# ---------------------------------------------------------------------------
# 4. No implicit I/O at import time (zero top-level Call nodes)
# ---------------------------------------------------------------------------


def _top_level_calls(tree: ast.Module):
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            yield stmt.value
        elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            yield stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(
            stmt.value, ast.Call
        ):
            yield stmt.value


def test_no_top_level_call_nodes() -> None:
    for basename, text in _sources().items():
        calls = list(_top_level_calls(ast.parse(text)))
        assert calls == [], (
            f"{basename} carries a top-level call (implicit I/O at import time)"
        )
