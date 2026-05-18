"""Stage 22.1 file-scope / vocabulary boundary tests.

Pins the 22.1 scope at the file and identifier level:

  * The Stage 22 production tree contains exactly the locked
    five files (``__init__.py``, ``constants.py``, ``errors.py``,
    ``ingest_contracts.py``, ``failure_classification.py``).
  * Forbidden 22.1 production filenames (jsonl writers, dedupe
    ledger implementations, raw capture writers, bounded runners,
    retry policies, real adapters/transports, scheduler/daemon
    files, manifest writers) do not exist.
  * No production module's identifier vocabulary introduces a
    Stage 22-forbidden symbol (scheduler / daemon / orchestrator
    / run_loop / worker / telegram / axiom / jito / eligibility).
  * No production module uses ``while`` / ``async for`` (those
    semantics are forbidden in 22.1).
  * Finite ``for`` loops are ALLOWED in pure helpers if needed --
    the test does NOT globally ban them.
  * No production module contains a ``__name__ == "__main__"``
    guard or a ``main`` / ``cli`` / ``entrypoint`` top-level
    function (no CLI surface in 22.1).
  * No production module contains a URL literal, webhook
    hostname, or ``bot.db`` reference.
  * No production module has a top-level call to a forbidden
    I/O / sleep / persistence callable.
  * Importing every production module is side-effect-free at the
    top level (only declarations).
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage22.constants import STAGE22_FORBIDDEN_VOCABULARY


STAGE22_ROOT: Path = Path(__file__).parent.parent.parent / "stage22"


# ---------------------------------------------------------------------------
# Locked production / forbidden file sets
# ---------------------------------------------------------------------------


_LOCKED_PRODUCTION_FILENAMES: frozenset[str] = frozenset({
    "__init__.py",
    "constants.py",
    "errors.py",
    "ingest_contracts.py",
    "failure_classification.py",
})


# Filenames that MUST NOT exist under PHX2/stage22/ in 22.1.
# Each name corresponds to behaviour reserved for Stage 22.2+
# or strictly later.
_FORBIDDEN_PRODUCTION_FILENAMES: tuple[str, ...] = (
    # Ledger implementations
    "dedupe_ledger.py",
    "dedupe_ledger_jsonl.py",
    "dedupe_ledger_sqlite.py",
    "dedupe_ledger_in_memory.py",
    "in_memory_ledger.py",
    # Capture writer implementations
    "raw_capture_writer.py",
    "jsonl_writer.py",
    "jsonl_dedupe_ledger.py",
    "capture_writer.py",
    # Runner / orchestrator
    "ingest_runner.py",
    "bounded_runner.py",
    "runner.py",
    "scheduler.py",
    "daemon.py",
    "orchestrator.py",
    "run_loop.py",
    # Retry execution
    "retry_policy.py",
    "backoff.py",
    "reconnect.py",
    # Real adapter / transport construction
    "provider_adapter.py",
    "provider_adapter_helius.py",
    "transport.py",
    "discord_transport.py",
    # Config / env-read seam (22.1 has none)
    "config.py",
    "live_secrets_boundary.py",
    # Manifest writers (22.1 has none)
    "stage22_1_manifest.py",
    "stage22_manifest.py",
)


# Forbidden Stage 22.1 sub-trees (subdirectory presence test).
_FORBIDDEN_PRODUCTION_SUBDIRS: tuple[str, ...] = (
    "ledger",
    "writers",
    "runners",
    "transports",
    "adapters",
)


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "https://",
    "http://",
    "wss://",
    "ws://",
    "discord.com",
    "discordapp.com",
    "hooks.slack.com",
)


# Callable names a Stage 22.1 production module must NEVER invoke
# at top level. Production modules are declarations + class /
# function definitions only.
_FORBIDDEN_TOP_LEVEL_CALL_NAMES: tuple[str, ...] = (
    "open",
    "socket",
    "urlopen",
    "requests",
    "httpx",
    "aiohttp",
    "grpc",
    "connect",
    "request",
    "post",
    "get",
    "sleep",
)


# CLI / sleep modules a Stage 22.1 production module must NEVER import.
_FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES: frozenset[str] = frozenset({
    "argparse",
    "click",
    "typer",
    "fire",
    "docopt",
    "time",
    "asyncio",
})


# File-persistence modules a Stage 22.1 production module must NEVER
# import. ``json`` is whitelisted at the import level because the
# classifier mapping table is in-memory only; no production module
# in 22.1 actually imports json yet, but the import is harmless if
# a future classifier helper needs it for hashing. (sqlite3 /
# sqlalchemy are caught by the import-boundary scanner separately.)
_FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES: frozenset[str] = frozenset({
    "pathlib",
    "shutil",
    "tempfile",
    "csv",
})


def _iter_production_modules() -> list[Path]:
    return [
        p for p in STAGE22_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# File scope
# ---------------------------------------------------------------------------


def test_stage22_root_directory_exists():
    assert STAGE22_ROOT.is_dir(), (
        f"Stage 22 production root {STAGE22_ROOT} must exist"
    )


def test_locked_production_files_all_exist():
    for name in _LOCKED_PRODUCTION_FILENAMES:
        path = STAGE22_ROOT / name
        assert path.is_file(), (
            f"Stage 22.1 requires production file {name}"
        )


def test_no_extra_production_files_exist():
    files = {
        p.name
        for p in STAGE22_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    extra = files - _LOCKED_PRODUCTION_FILENAMES
    assert not extra, (
        f"Stage 22.1 production tree has unexpected files: {sorted(extra)}"
    )


def test_forbidden_production_filenames_do_not_exist():
    for name in _FORBIDDEN_PRODUCTION_FILENAMES:
        path = STAGE22_ROOT / name
        assert not path.exists(), (
            f"Stage 22.1 scope violation: {name} must not exist"
        )


def test_no_forbidden_production_subdirs():
    for name in _FORBIDDEN_PRODUCTION_SUBDIRS:
        path = STAGE22_ROOT / name
        assert not path.exists(), (
            f"Stage 22.1 scope violation: subdirectory {name!r} must "
            "not exist"
        )


# ---------------------------------------------------------------------------
# Top-level side-effect freedom
# ---------------------------------------------------------------------------


def test_every_production_module_has_side_effect_free_top_level():
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
        tree = ast.parse(_read_source(py_file))
        for node in tree.body:
            assert isinstance(node, allowed_top_level), (
                f"{py_file}: unexpected top-level node "
                f"{type(node).__name__}"
            )


# ---------------------------------------------------------------------------
# Top-level forbidden calls
# ---------------------------------------------------------------------------


class _TopLevelCallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.depth: int = 0
        self.calls: list[ast.Call] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        if self.depth == 0:
            self.calls.append(node)
        self.generic_visit(node)


def _collect_top_level_call_names(source: str) -> set[str]:
    tree = ast.parse(source)
    collector = _TopLevelCallCollector()
    collector.visit(tree)
    names: set[str] = set()
    for call in collector.calls:
        func: ast.expr = call.func
        while isinstance(func, ast.Attribute):
            names.add(func.attr)
            func = func.value
        if isinstance(func, ast.Name):
            names.add(func.id)
    return names


def test_no_forbidden_top_level_calls():
    for py_file in _iter_production_modules():
        names = _collect_top_level_call_names(_read_source(py_file))
        leaked = sorted(set(names) & set(_FORBIDDEN_TOP_LEVEL_CALL_NAMES))
        assert not leaked, (
            f"{py_file}: forbidden top-level call(s) {leaked}"
        )


# ---------------------------------------------------------------------------
# CLI surface absence
# ---------------------------------------------------------------------------


def test_no_production_module_has_dunder_main_guard():
    """No ``if __name__ == '__main__':`` block anywhere in Stage 22.1."""
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                participants: list[ast.expr] = [node.left]
                participants.extend(node.comparators)
                has_dunder_name = any(
                    isinstance(p, ast.Name) and p.id == "__name__"
                    for p in participants
                )
                has_dunder_main = any(
                    isinstance(p, ast.Constant)
                    and p.value == "__main__"
                    for p in participants
                )
                assert not (has_dunder_name and has_dunder_main), (
                    f"{py_file}: forbidden __name__ == '__main__' guard"
                )


def test_no_production_module_defines_top_level_main_or_cli():
    forbidden_entrypoint_names: frozenset[str] = frozenset({
        "main",
        "cli",
        "entrypoint",
    })
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in tree.body:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                assert node.name not in forbidden_entrypoint_names, (
                    f"{py_file}: forbidden CLI-style entrypoint "
                    f"function {node.name!r}"
                )


def test_no_production_module_imports_cli_or_sleep_libs():
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert (
                        top not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES
                    ), f"{py_file}: forbidden CLI/sleep import {alias.name!r}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0]
                assert (
                    top not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES
                ), f"{py_file}: forbidden CLI/sleep from-import {mod!r}"


def test_no_production_module_imports_file_persistence_libs():
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert (
                        top
                        not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES
                    ), (
                        f"{py_file}: forbidden file-persistence "
                        f"import {alias.name!r}"
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0]
                assert (
                    top
                    not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES
                ), (
                    f"{py_file}: forbidden file-persistence from-import "
                    f"{mod!r}"
                )


# ---------------------------------------------------------------------------
# Loop discipline
# ---------------------------------------------------------------------------


def test_no_production_module_uses_while_loop():
    """``while`` loops are forbidden in 22.1 production code.

    Finite ``for`` loops in pure helpers remain allowed per the
    22.1 design-lock correction §1; only ``while`` (and
    ``async for``) is fully banned.
    """
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            assert not isinstance(node, ast.While), (
                f"{py_file}: forbidden ``while`` loop in Stage 22.1 "
                "production code"
            )


def test_no_production_module_uses_async_for_loop():
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            assert not isinstance(node, ast.AsyncFor), (
                f"{py_file}: forbidden ``async for`` loop in Stage "
                "22.1 production code"
            )


def test_no_production_module_uses_async_function_def():
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            assert not isinstance(node, ast.AsyncFunctionDef), (
                f"{py_file}: forbidden ``async def`` in Stage 22.1 "
                "production code (no event loop / async runner)"
            )


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


def test_no_url_literal_in_production_source():
    for py_file in _iter_production_modules():
        source = _read_source(py_file)
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{py_file}: forbidden URL literal {needle!r} in source"
            )


def test_no_bot_db_reference_in_production_source():
    for py_file in _iter_production_modules():
        source = _read_source(py_file)
        assert "bot.db" not in source, (
            f"{py_file}: forbidden 'bot.db' reference in source"
        )


# ---------------------------------------------------------------------------
# Forbidden identifier vocabulary scan
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
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
        elif isinstance(node, ast.alias):
            idents.add(node.name)
            if node.asname:
                idents.add(node.asname)
    return idents


def test_no_production_identifier_contains_forbidden_vocabulary():
    """Substring scan: every identifier in every Stage 22 production
    module must avoid each entry of ``STAGE22_FORBIDDEN_VOCABULARY``.

    The scan operates on identifier-position names extracted from
    the AST; string literals (including docstrings and the locked
    forbidden-vocabulary tuple in ``constants.py``) are NOT scanned.
    """
    constants_path = STAGE22_ROOT / "constants.py"
    for py_file in _iter_production_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE22_FORBIDDEN_VOCABULARY:
                # The locked vocabulary tuple lives in constants.py
                # as identifier `STAGE22_FORBIDDEN_VOCABULARY`; the
                # substring scan would otherwise hit that
                # declaration via string literals which the AST
                # scan correctly excludes. No explicit allow-list
                # is needed because string literals are not
                # extracted by _extract_all_identifiers.
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains "
                    f"forbidden vocabulary substring {forbidden!r}"
                )
        # Silence unused-variable lint in older toolchains.
        _ = constants_path


def test_no_production_class_or_func_defines_forbidden_scope_name():
    """No top-level class or function with a forbidden scope name."""
    forbidden_named_defs: tuple[str, ...] = (
        "Scheduler",
        "Daemon",
        "Orchestrator",
        "RunLoop",
        "Worker",
        "PublicDispatch",
        "SubscriberDispatch",
        "PaidDispatch",
    )
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                assert node.name not in forbidden_named_defs, (
                    f"{py_file}: forbidden scope symbol {node.name!r}"
                )
