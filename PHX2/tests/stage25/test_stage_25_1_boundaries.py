"""Stage 25.1 file-scope / import-boundary / vocabulary tests.

Pins the 25.1 scope at the file and identifier level:

  * The Stage 25 production tree contains EXACTLY the locked seven
    files (``__init__.py``, ``constants.py``, ``errors.py``,
    ``models.py``, ``measurement_contracts.py``, ``input_reader.py``,
    ``stage25_manifest.py``).
  * Forbidden 25.1 production filenames (later-stage measurers,
    candidate-builders, source-reconciliation modules, runners,
    artifact writers, alert dispatchers, scheduler files) do not
    exist.
  * No production function carries an ambiguous domain-builder
    name (``build_ath_candidate`` / ``build_source_reconciliation``
    without the ``_record`` suffix). Record validators MUST carry
    the ``_record`` suffix so the contract surface is unambiguous.
  * No production module imports Stage 21 / Stage 22 / Stage 23 /
    Stage 24 production modules.
  * No production module imports a Phoenix1 module.
  * No production module imports a PHX2 runtime-layer module
    (``PHX2.db`` / ``PHX2.repositories`` / ``PHX2.config`` /
    ``PHX2.models`` / ``PHX2.services`` / ``PHX2.dispatch`` /
    ``PHX2.filters`` / ``PHX2.integrations`` / ``PHX2.renderers`` /
    ``PHX2.scripts`` / ``PHX2.analysis``).
  * No production module imports a network / RPC / messaging / DB /
    scheduler / secrets-management library.
  * No production module reads ``os.environ`` / ``os.getenv``.
  * No production module's identifier vocabulary introduces a
    Stage 25-forbidden substring.
  * No production identifier carries any Stage 24 execution-fee
    vocabulary substring (``axiom`` / ``jito`` /
    ``compute_budget`` / ``router_fee``).
  * Stage 25's own vocabulary (``migration`` / ``birdeye`` /
    ``dexscreener`` / ``ath`` / ``peak`` / ``source`` /
    ``reconciliation`` / ``candidate`` / ``price`` / ``window`` /
    ``measurement`` / ``observation`` / ``swap_replay``) is NOT
    falsely banned.
  * No production module writes to disk (no ``write_text`` /
    ``write_bytes``).
  * No production module contains a URL literal or webhook host
    literal.
  * No production module contains a top-level call to a forbidden
    I/O / sleep / persistence callable.
  * No production module defines a CLI surface.
  * Importing every production module is side-effect-free at the
    top level.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage25.constants import (
    STAGE25_FORBIDDEN_ROUTING_TOKENS,
    STAGE25_FORBIDDEN_STAGE24_EXECUTION_FEE_VOCABULARY,
    STAGE25_FORBIDDEN_VOCABULARY,
)


STAGE25_ROOT: Path = Path(__file__).parent.parent.parent / "stage25"


# ---------------------------------------------------------------------------
# Locked production / forbidden file sets
# ---------------------------------------------------------------------------


_LOCKED_PRODUCTION_FILENAMES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "constants.py",
        "errors.py",
        "models.py",
        "measurement_contracts.py",
        "input_reader.py",
        "stage25_manifest.py",
        # Stage 25.2 additions -- listed here so the Stage 25.1
        # inventory check does not flag them as unexpected files.
        # The Stage 25.2 boundary test pins them explicitly.
        "migration_observation.py",
        "migration_measurement.py",
        # Stage 25.3 additions -- listed here so the Stage 25.1
        # inventory check does not flag them as unexpected files.
        # The Stage 25.3 boundary test pins them explicitly.
        "price_observation.py",
        "price_window.py",
        # Stage 25.4 additions -- listed here so the Stage 25.1
        # inventory check does not flag them as unexpected files.
        # The Stage 25.4 boundary test pins them explicitly.
        "ath_candidate.py",
        # Stage 25.5 additions -- listed here so the Stage 25.1
        # inventory check does not flag them as unexpected files.
        # The Stage 25.5 boundary test pins them explicitly.
        "source_reconciliation.py",
        # Stage 25.6 additions -- listed here so the Stage 25.1
        # inventory check does not flag them as unexpected files.
        # The Stage 25.6 boundary test pins them explicitly.
        "runner.py",
        "artifact_writer.py",
        "summary.py",
    }
)


_PATHLIB_ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "input_reader.py",
        "stage25_manifest.py",
        # Stage 25.6 deterministic writer reads + writes operator-
        # supplied output paths; pathlib is required for ``Path``
        # arithmetic and atomic temp-file promotion.
        "artifact_writer.py",
    }
)


_FORBIDDEN_PRODUCTION_FILENAMES: tuple[str, ...] = (
    # Reserved-but-not-used measurer / projector / candidate-
    # building / reconciliation filenames (later sub-stages).
    # Stage 25.1 explicitly forbids any module implementing ATH
    # candidate-building or source reconciliation domain logic.
    # NOTE: ``source_reconciliation.py`` graduated into Stage 25.5
    # and is part of the locked inventory above; it is no longer
    # listed here.
    # NOTE: ``runner.py`` / ``artifact_writer.py`` / ``summary.py``
    # graduated into Stage 25.6 and are part of the locked
    # inventory above; they are no longer listed here.
    "migration_measurer.py",
    "ath_reconciler.py",
    "ath_measurer.py",
    "price_projector.py",
    "source_reconciler.py",
    # Reserved-but-not-used runner / writer filenames.
    "stage25_runner.py",
    "evaluations_writer.py",
    "summary_writer.py",
    "csv_writer.py",
    # Scheduler / daemon
    "scheduler.py",
    "daemon.py",
    "orchestrator.py",
    # Env / secrets seam
    "config.py",
    "secrets.py",
    "env.py",
    # Transport / routing
    "transport.py",
    "discord.py",
    "telegram.py",
    "dispatcher.py",
    # External primitives (wrong stage)
    "birdeye.py",
    "dexscreener.py",
    "x_api.py",
    "social.py",
)


_FORBIDDEN_PRODUCTION_SUBDIRS: tuple[str, ...] = (
    "measurers",
    "reconcilers",
    "projectors",
    "runners",
    "writers",
    "transports",
    "adapters",
    "social",
)


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
)


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
    "write_text",
    "write_bytes",
)


_FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES: frozenset[str] = frozenset(
    {
        "argparse",
        "click",
        "typer",
        "fire",
        "docopt",
        "time",
        "asyncio",
    }
)


_FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES: frozenset[str] = frozenset(
    {
        "pathlib",
        "shutil",
        "tempfile",
        "csv",
    }
)


_FORBIDDEN_PRIOR_STAGE_PRODUCTION_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
)


_FORBIDDEN_PHX2_RUNTIME_PREFIXES: tuple[str, ...] = (
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
    # Provider clients
    "helius",
    "jupiter",
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


_DYNAMIC_IMPORT_FUNC_NAMES: frozenset[str] = frozenset(
    {
        "import_module",
        "__import__",
    }
)


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_production_modules() -> list[Path]:
    return [
        p
        for p in STAGE25_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_import_targets_from_source(
    source: str,
) -> tuple[set[str], set[str]]:
    tree = ast.parse(source)
    modules: set[str] = set()
    full_targets: set[str] = set()

    dynamic_import_aliases: set[str] = set(_DYNAMIC_IMPORT_FUNC_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name in _DYNAMIC_IMPORT_FUNC_NAMES:
                    bound_name = alias.asname or alias.name
                    dynamic_import_aliases.add(bound_name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                full_targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
                full_targets.add(mod)
            for alias in node.names:
                if mod:
                    full_targets.add(f"{mod}.{alias.name}")
        elif isinstance(node, ast.Call):
            func = node.func
            is_dynamic_import = False
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "import_module"
            ):
                is_dynamic_import = True
            elif (
                isinstance(func, ast.Name)
                and func.id in dynamic_import_aliases
            ):
                is_dynamic_import = True
            if is_dynamic_import and node.args:
                first = node.args[0]
                if (
                    isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                ):
                    modules.add(first.value)
                    full_targets.add(first.value)
    return modules, full_targets


def _collect_modules(path: Path) -> set[str]:
    modules, _ = _collect_import_targets_from_source(_read_source(path))
    return modules


def _collect_full_targets(path: Path) -> set[str]:
    _, full = _collect_import_targets_from_source(_read_source(path))
    return full


# ---------------------------------------------------------------------------
# File scope
# ---------------------------------------------------------------------------


def test_stage25_root_directory_exists():
    assert STAGE25_ROOT.is_dir(), (
        f"Stage 25 production root {STAGE25_ROOT} must exist"
    )


def test_locked_production_files_all_exist():
    for name in _LOCKED_PRODUCTION_FILENAMES:
        path = STAGE25_ROOT / name
        assert path.is_file(), (
            f"Stage 25.1 requires production file {name}"
        )


def test_no_extra_production_files_exist():
    files = {
        p.name
        for p in STAGE25_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    extra = files - _LOCKED_PRODUCTION_FILENAMES
    assert not extra, (
        f"Stage 25.1 production tree has unexpected files: "
        f"{sorted(extra)}"
    )


def test_forbidden_production_filenames_do_not_exist():
    for name in _FORBIDDEN_PRODUCTION_FILENAMES:
        path = STAGE25_ROOT / name
        assert not path.exists(), (
            f"Stage 25.1 scope violation: {name} must not exist"
        )


def test_no_forbidden_production_subdirs():
    for name in _FORBIDDEN_PRODUCTION_SUBDIRS:
        path = STAGE25_ROOT / name
        assert not path.exists(), (
            f"Stage 25.1 scope violation: subdirectory {name!r} must not "
            "exist"
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
        ast.Expr,
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
    forbidden_entrypoint_names: frozenset[str] = frozenset(
        {"main", "cli", "entrypoint"}
    )
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


# ---------------------------------------------------------------------------
# CLI / sleep / persistence library imports
# ---------------------------------------------------------------------------


def test_no_production_module_imports_cli_or_sleep_libs():
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert (
                        top
                        not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES
                    ), (
                        f"{py_file}: forbidden CLI/sleep import "
                        f"{alias.name!r}"
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0]
                assert (
                    top not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES
                ), (
                    f"{py_file}: forbidden CLI/sleep from-import {mod!r}"
                )


def test_no_production_module_imports_unauthorized_file_persistence_libs():
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        allow_pathlib = py_file.name in _PATHLIB_ALLOWED_FILES
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top == "pathlib" and allow_pathlib:
                        continue
                    assert (
                        top
                        not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES
                    ), (
                        f"{py_file}: forbidden file-persistence import "
                        f"{alias.name!r}"
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0]
                if top == "pathlib" and allow_pathlib:
                    continue
                assert (
                    top
                    not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES
                ), (
                    f"{py_file}: forbidden file-persistence from-import "
                    f"{mod!r}"
                )


# ---------------------------------------------------------------------------
# Import boundary
# ---------------------------------------------------------------------------


def test_no_phoenix1_imports():
    for py_file in _iter_production_modules():
        for target in _collect_full_targets(py_file):
            assert not target.startswith("phoenix1"), (
                f"{py_file}: forbidden phoenix1 import target {target!r}"
            )
            assert not target.startswith("Phoenix1"), (
                f"{py_file}: forbidden Phoenix1 import target {target!r}"
            )


def test_no_prior_stage_production_imports():
    for py_file in _iter_production_modules():
        for target in _collect_full_targets(py_file):
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PRODUCTION_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{py_file}: forbidden prior-stage import {target!r}"
                )


def test_no_phx2_runtime_layer_imports():
    for py_file in _iter_production_modules():
        for target in _collect_full_targets(py_file):
            for forbidden in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{py_file}: forbidden PHX2 runtime-layer target "
                    f"{target!r}"
                )


def test_no_forbidden_runtime_module_patterns():
    for py_file in _iter_production_modules():
        for module in _collect_modules(py_file):
            lower = module.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{py_file}: forbidden module pattern {pattern!r} in "
                    f"import target {module!r}"
                )


# ---------------------------------------------------------------------------
# Env-read boundary
# ---------------------------------------------------------------------------


def _module_reads_env_in_source(source: str) -> bool:
    tree = ast.parse(source)
    os_aliases: set[str] = set()
    env_call_aliases: set[str] = set()
    env_attr_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "os":
                for alias in node.names:
                    bound_name = alias.asname or alias.name
                    if alias.name in ("environ", "environb"):
                        env_attr_aliases.add(bound_name)
                    elif alias.name == "getenv":
                        env_call_aliases.add(bound_name)
            elif mod == "os.environ" or mod.startswith("os.environ."):
                return True

    if env_attr_aliases or env_call_aliases:
        return True

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in _ENV_ATTR_NAMES
            ):
                return True
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in os_aliases
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value in _ENV_ATTR_NAMES
            ):
                return True
    return False


def test_no_stage25_module_reads_environ():
    for py_file in _iter_production_modules():
        assert not _module_reads_env_in_source(_read_source(py_file)), (
            f"{py_file}: forbidden env-read pattern. Stage 25 contract: "
            "no Stage 25 module may read the process environment."
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


# ---------------------------------------------------------------------------
# Identifier vocabulary scan
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
    """Substring scan: every identifier in every Stage 25 production
    module must avoid each entry of ``STAGE25_FORBIDDEN_VOCABULARY``.
    """
    for py_file in _iter_production_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE25_FORBIDDEN_VOCABULARY:
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains forbidden "
                    f"vocabulary substring {forbidden!r}"
                )


def test_no_production_identifier_contains_stage24_execution_fee_vocabulary():
    """Stage 25 must NOT reuse Stage 24 execution-fee identifiers.

    The boundary scanner refuses any Stage 25 production identifier
    that contains a Stage 24 execution-fee substring (``axiom`` /
    ``jito`` / ``compute_budget`` / ``router_fee``).
    """
    for py_file in _iter_production_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE25_FORBIDDEN_STAGE24_EXECUTION_FEE_VOCABULARY:
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains Stage 24 "
                    f"execution-fee substring {forbidden!r}"
                )


def test_no_production_identifier_contains_forbidden_routing_token():
    """Every identifier must avoid each
    ``STAGE25_FORBIDDEN_ROUTING_TOKENS`` token.
    """
    for py_file in _iter_production_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE25_FORBIDDEN_ROUTING_TOKENS:
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains forbidden "
                    f"routing-token substring {forbidden!r}"
                )


def _iter_production_function_names(py_file: Path) -> set[str]:
    tree = ast.parse(_read_source(py_file))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


_FORBIDDEN_DOMAIN_BUILDER_NAMES: frozenset[str] = frozenset(
    {
        # Stage 25.1 must not implement ATH candidate-building or
        # source reconciliation domain logic. Pure record validators
        # are allowed but must carry the ``_record`` suffix to make
        # the contract surface unambiguous.
        "build_ath_candidate",
        "build_source_reconciliation",
        # Names that would imply downstream domain logic from later
        # sub-stages.
        "reconcile_sources",
        "build_ath_measurement",
        "build_migration_measurement",
        "select_ath_peak",
        "select_migration_boundary",
        "consolidate_sources",
    }
)


def test_no_production_function_defines_ambiguous_domain_builder():
    """Stage 25.1 ships record validators only.

    A production function named ``build_ath_candidate`` /
    ``build_source_reconciliation`` (without the disambiguating
    ``_record`` suffix) reads as "implements ATH candidate
    construction / source reconciliation logic" -- which is a
    Stage 25.3 / Stage 25.4 surface, not Stage 25.1. Record
    validators MUST carry the ``_record`` suffix so the contract
    surface is unambiguous.
    """
    for py_file in _iter_production_modules():
        function_names = _iter_production_function_names(py_file)
        leaked = sorted(function_names & _FORBIDDEN_DOMAIN_BUILDER_NAMES)
        assert not leaked, (
            f"{py_file}: forbidden domain-builder function name(s) "
            f"{leaked}; Stage 25.1 ships record validators only -- "
            "rename to ``*_record`` or remove."
        )


def test_record_validator_variants_are_present_in_models_source():
    """Sanity: the renamed record-validator functions exist in models.

    Pins the rename: ``build_ath_candidate_record`` and
    ``build_source_reconciliation_record`` are the canonical
    record-validator names.
    """
    models_path = STAGE25_ROOT / "models.py"
    models_function_names = _iter_production_function_names(models_path)
    assert "build_ath_candidate_record" in models_function_names
    assert "build_source_reconciliation_record" in models_function_names
    # And the un-suffixed names must NOT appear.
    assert "build_ath_candidate" not in models_function_names
    assert "build_source_reconciliation" not in models_function_names


def test_stage25_vocabulary_is_not_falsely_banned():
    """Stage 25's own vocabulary MUST NOT be on the Stage 25 forbidden
    vocabulary list. These are the stage's domain concepts and must
    remain usable as identifier parts.
    """
    forbidden = set(STAGE25_FORBIDDEN_VOCABULARY)
    for stage25_word in (
        "migration",
        "birdeye",
        "dexscreener",
        "ath",
        "peak",
        "source",
        "reconciliation",
        "candidate",
        "price",
        "window",
        "measurement",
        "observation",
        "swap_replay",
    ):
        assert stage25_word not in forbidden, (
            f"Stage 25 vocabulary word {stage25_word!r} must not be on "
            "the forbidden list"
        )


# ---------------------------------------------------------------------------
# No-write discipline
# ---------------------------------------------------------------------------


def test_no_production_module_calls_write_text_or_write_bytes():
    """Stage 25.1 production code MUST NOT write to disk.

    The Stage 25.5 artifact writer is the future home for any
    on-disk writing. 25.1 only reads inputs and hashes files; it
    does not produce any output file.
    """
    forbidden_attrs: frozenset[str] = frozenset(
        {"write_text", "write_bytes"}
    )
    for py_file in _iter_production_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_attrs, (
                    f"{py_file}: forbidden attribute reference "
                    f"{node.attr!r}; Stage 25.1 has no artifact writer"
                )


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


def test_every_production_module_imports_cleanly():
    """Every locked production module must import without side effects."""
    import importlib

    expected = {
        "PHX2.stage25",
        "PHX2.stage25.constants",
        "PHX2.stage25.errors",
        "PHX2.stage25.models",
        "PHX2.stage25.measurement_contracts",
        "PHX2.stage25.input_reader",
        "PHX2.stage25.stage25_manifest",
        # Stage 25.2 additions.
        "PHX2.stage25.migration_observation",
        "PHX2.stage25.migration_measurement",
        # Stage 25.3 additions.
        "PHX2.stage25.price_observation",
        "PHX2.stage25.price_window",
        # Stage 25.4 additions.
        "PHX2.stage25.ath_candidate",
        # Stage 25.5 additions.
        "PHX2.stage25.source_reconciliation",
        # Stage 25.6 additions.
        "PHX2.stage25.runner",
        "PHX2.stage25.artifact_writer",
        "PHX2.stage25.summary",
    }
    for name in expected:
        module = importlib.import_module(name)
        assert module is not None


# ---------------------------------------------------------------------------
# Negative-fixture sanity (collector catches the cases it claims to)
# ---------------------------------------------------------------------------


def _has_forbidden_prior_stage(source: str) -> bool:
    _, full_targets = _collect_import_targets_from_source(source)
    for target in full_targets:
        for forbidden in _FORBIDDEN_PRIOR_STAGE_PRODUCTION_PREFIXES:
            if target.startswith(forbidden):
                return True
    return False


def test_collector_catches_phx2_stage24_import():
    source = "from PHX2.stage24.constants import STAGE_VERSION\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_phx2_stage23_import():
    source = "from PHX2.stage23.constants import STAGE23_VERSION\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_dunder_import_literal():
    source = "__import__('PHX2.stage24')\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_does_not_catch_docstring_mention():
    source = (
        '"""Docstring mentions PHX2.stage24 but does not import it."""\n'
    )
    assert not _has_forbidden_prior_stage(source)


def test_env_detector_catches_plain_os_environ():
    source = "import os\nx = os.environ['KEY']\n"
    assert _module_reads_env_in_source(source)


def test_env_detector_catches_from_os_import_getenv():
    source = "from os import getenv\nx = getenv('KEY')\n"
    assert _module_reads_env_in_source(source)


def test_env_detector_ignores_docstring_mention():
    source = '"""os.environ never read."""\n'
    assert not _module_reads_env_in_source(source)
