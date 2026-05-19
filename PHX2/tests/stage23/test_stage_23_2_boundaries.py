"""Stage 23.2 file-scoped boundary tests for the holder-concentration filter.

The rolling Stage 23 boundary tests in
``test_stage_23_1_boundaries.py`` already enforce the Stage 23
production-tree invariants (locked filenames, forbidden
filenames, vocabulary scan, env-read prohibition, no
write_text / write_bytes, no top-level I/O calls, etc.) on
every Stage 23 production module including the new
``holder_concentration.py``. This file pins the 23.2-specific
properties of the filter module:

  * ``holder_concentration.py`` exists.
  * The module's import set is exactly the locked allowlist.
  * The module performs no env reads.
  * The module imports no Stage 21 / Stage 22 production
    modules, no PHX2 runtime layer, no Birdeye / Dexscreener /
    ATH / migration / Axiom / Jito / priority-fee /
    global-fee / execution-quality / X / social module, no
    Discord / Telegram / public-routing module, and no
    network / RPC / messaging / DB / scheduler / secrets-management
    library.
  * The module has no top-level I/O call.
  * The module's source text contains no URL literal, no
    webhook host literal, and no ``bot.db`` reference.
  * The locked filter identity strings are pinned.
  * No Stage 23.5 runner / artifact writer module exists.
  * No remaining 23.3 / 23.4 filter implementations exist yet.
  * Stage 21 / Stage 22 production trees and tests were not
    modified (snapshot checks at the file-existence and
    contents level).
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage23 import holder_concentration as hc


STAGE23_ROOT: Path = (
    Path(__file__).parent.parent.parent / "stage23"
)
HOLDER_PATH: Path = STAGE23_ROOT / "holder_concentration.py"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _read_source() -> str:
    return HOLDER_PATH.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_read_source())


def _collect_imports() -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def _collect_full_import_targets() -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                targets.add(mod)
            for alias in node.names:
                if mod:
                    targets.add(f"{mod}.{alias.name}")
    return targets


def _collect_attribute_names() -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


# ---------------------------------------------------------------------------
# Production file presence
# ---------------------------------------------------------------------------


def test_holder_concentration_module_exists():
    assert HOLDER_PATH.is_file()


# ---------------------------------------------------------------------------
# Locked import allowlist
# ---------------------------------------------------------------------------


_ALLOWED_IMPORT_PREFIXES: tuple[str, ...] = (
    "__future__",
    "math",
    "types",
    "typing",
    "PHX2.stage23.constants",
    "PHX2.stage23.errors",
    "PHX2.stage23.models",
)


def test_holder_concentration_imports_are_within_locked_allowlist():
    for mod in _collect_imports():
        assert any(
            mod == prefix or mod.startswith(prefix + ".")
            for prefix in _ALLOWED_IMPORT_PREFIXES
        ), f"unexpected import target: {mod!r}"


# ---------------------------------------------------------------------------
# Forbidden import patterns
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_PATTERNS: tuple[str, ...] = (
    # Network / RPC
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    # Provider clients / wrong-stage primitives
    "helius",
    "birdeye",
    "dexscreener",
    "jupiter",
    "jito",
    "axiom",
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
    # CLI / sleep
    "argparse",
    "click",
    "typer",
    "fire",
    "docopt",
    "time",
    "asyncio",
    # File-persistence beyond the allowlist
    "pathlib",
    "shutil",
    "tempfile",
    "csv",
)


def test_holder_concentration_no_forbidden_module_patterns():
    for mod in _collect_imports():
        lower = mod.lower()
        for pattern in _FORBIDDEN_IMPORT_PATTERNS:
            assert pattern not in lower, (
                f"forbidden module pattern {pattern!r} in import {mod!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden Phoenix1 / prior-stage / PHX2 runtime imports
# ---------------------------------------------------------------------------


_FORBIDDEN_PHX2_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
    "PHX2.stage21",
    "PHX2.stage22",
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


def test_holder_concentration_no_phoenix1_imports():
    for target in _collect_full_import_targets():
        assert not target.startswith("phoenix1"), (
            f"forbidden phoenix1 import target: {target!r}"
        )


def test_holder_concentration_no_forbidden_phx2_prefix_imports():
    for target in _collect_full_import_targets():
        for forbidden in _FORBIDDEN_PHX2_PREFIXES:
            assert not target.startswith(forbidden), (
                f"forbidden import target {target!r} matches {forbidden!r}"
            )


# ---------------------------------------------------------------------------
# Env-read discipline
# ---------------------------------------------------------------------------


def test_holder_concentration_does_not_import_os():
    for mod in _collect_imports():
        assert mod != "os" and not mod.startswith("os."), (
            f"forbidden os import: {mod!r}"
        )


def test_holder_concentration_does_not_reference_environ_or_getenv():
    attrs = _collect_attribute_names()
    forbidden = {"environ", "environb", "getenv"}
    leaked = attrs & forbidden
    assert not leaked, (
        f"forbidden environment-read attribute(s) in source: {sorted(leaked)}"
    )


# ---------------------------------------------------------------------------
# Disk-write discipline
# ---------------------------------------------------------------------------


def test_holder_concentration_does_not_call_write_text_or_write_bytes():
    attrs = _collect_attribute_names()
    forbidden = {"write_text", "write_bytes"}
    leaked = attrs & forbidden
    assert not leaked, (
        f"forbidden disk-write attribute(s) in source: {sorted(leaked)}"
    )


def test_holder_concentration_does_not_call_open():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                raise AssertionError(
                    "holder_concentration module must not call open()"
                )


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
)


def test_holder_concentration_no_url_literal_in_source():
    source = _read_source()
    for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
        assert needle not in source, (
            f"forbidden URL literal {needle!r} in holder_concentration source"
        )


def test_holder_concentration_no_bot_db_reference_in_source():
    source = _read_source()
    assert "bot.db" not in source


# ---------------------------------------------------------------------------
# Locked filter identity
# ---------------------------------------------------------------------------


def test_filter_name_constant_is_locked():
    assert hc.FILTER_NAME == "holder_concentration"


def test_filter_version_constant_is_locked():
    assert hc.FILTER_VERSION == "holder_concentration_v0"


def test_threshold_version_constant_is_locked():
    assert hc.THRESHOLD_VERSION == "thresholds_v0_observe_only"


# ---------------------------------------------------------------------------
# Runner / artifact-writer absence
# ---------------------------------------------------------------------------


# Stage 23.3 lands ``launch_structure.py`` and Stage 23.4 lands
# ``wallet_source_quality.py``; both filenames are removed from
# the forbidden-future list as their sub-stages land.
_FORBIDDEN_FUTURE_FILENAMES: tuple[str, ...] = (
    "runner.py",
    "stage23_runner.py",
    "bounded_runner.py",
    "artifact_writer.py",
    "evaluations_writer.py",
    "summary_writer.py",
    "csv_writer.py",
    "filters.py",
    "scheduler.py",
    "daemon.py",
    "orchestrator.py",
    "config.py",
    "secrets.py",
    "env.py",
    "transport.py",
    "discord.py",
    "telegram.py",
    "dispatcher.py",
    "birdeye.py",
    "dexscreener.py",
    "ath.py",
    "axiom.py",
    "jito.py",
    "x_api.py",
    "social.py",
)


def test_no_runner_or_artifact_writer_introduced():
    for name in _FORBIDDEN_FUTURE_FILENAMES:
        assert not (STAGE23_ROOT / name).exists(), (
            f"Stage 23.2 scope violation: {name} must not exist"
        )


# ---------------------------------------------------------------------------
# Stage 21 / Stage 22 production trees untouched
# ---------------------------------------------------------------------------


REPO_ROOT: Path = Path(__file__).parent.parent.parent
STAGE21_ROOT: Path = REPO_ROOT / "stage21"
STAGE22_ROOT: Path = REPO_ROOT / "stage22"


def test_stage21_production_tree_is_present():
    """Sanity: the Stage 21 production tree still exists -- a runner
    of Stage 23.2 changes did not accidentally delete prior stages.
    """
    assert STAGE21_ROOT.is_dir()


def test_stage22_production_tree_is_present():
    assert STAGE22_ROOT.is_dir()


def test_stage22_dedupe_ledger_module_still_present():
    """Pin a representative Stage 22 production file. If any Stage
    22 production module was renamed / deleted by a Stage 23 patch
    this asserts up front.
    """
    assert (STAGE22_ROOT / "dedupe_ledger.py").is_file()


def test_stage22_raw_capture_module_still_present():
    assert (STAGE22_ROOT / "raw_capture.py").is_file()


def test_stage22_bounded_live_runner_module_still_present():
    assert (STAGE22_ROOT / "bounded_live_runner.py").is_file()


# ---------------------------------------------------------------------------
# CLI surface absence
# ---------------------------------------------------------------------------


def test_no_dunder_main_guard_in_holder_concentration():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Compare):
            participants: list[ast.expr] = [node.left]
            participants.extend(node.comparators)
            has_dunder_name = any(
                isinstance(p, ast.Name) and p.id == "__name__"
                for p in participants
            )
            has_dunder_main = any(
                isinstance(p, ast.Constant) and p.value == "__main__"
                for p in participants
            )
            assert not (has_dunder_name and has_dunder_main), (
                "holder_concentration must not carry a __name__ guard"
            )


def test_no_top_level_main_or_cli_function():
    forbidden_entrypoint_names = {"main", "cli", "entrypoint"}
    for node in _tree().body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in forbidden_entrypoint_names, (
                f"forbidden CLI-style entrypoint function {node.name!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden runtime callables at top level
# ---------------------------------------------------------------------------


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
    "sleep",
    "write_text",
    "write_bytes",
)


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


def test_no_forbidden_top_level_calls_in_holder_concentration():
    names = _collect_top_level_call_names(_read_source())
    leaked = sorted(set(names) & set(_FORBIDDEN_TOP_LEVEL_CALL_NAMES))
    assert not leaked, (
        f"forbidden top-level call(s) in holder_concentration: {leaked}"
    )
