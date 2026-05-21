"""Stage 25.5 file-scope / import-boundary / vocabulary tests.

Pins the 25.5 scope at the file and identifier level:

  * The Stage 25 production tree contains EXACTLY the 25.1 / 25.2 /
    25.3 / 25.4 files plus ``source_reconciliation.py``.
  * Forbidden future production filenames (runners, artifact writers,
    scheduler / daemon / dispatcher files) do not exist.
  * No new production module imports Stage 21 / Stage 22 / Stage 23 /
    Stage 24 production modules.
  * No new production module imports a PHX2 runtime-layer module.
  * No new production module imports a network / RPC / messaging /
    DB / scheduler / secrets-management library.
  * No new production module reads ``os.environ`` / ``os.getenv``.
  * No new production module's identifier vocabulary introduces a
    Stage 25-forbidden substring or a Stage 24 execution-fee
    substring.
  * No new production module contains a top-level call to a
    forbidden I/O / sleep / persistence callable.
  * No new production module contains a URL literal or webhook host
    literal.
  * No new production module defines a CLI surface.
  * No new production module introduces Stage 26 calibration /
    enforcement identifiers or Stage 27 X / social identifiers.
  * Stage 25.5 does NOT ship a runner, artifact writer, or
    deterministic output writer: identifier substrings
    ``runner`` / ``artifact_writer`` / ``writer`` / ``write_text`` /
    ``write_bytes`` MUST NOT appear in ``source_reconciliation.py``.
  * Stage 25.5's own vocabulary (``reconciliation`` / ``source`` /
    ``confidence`` / ``measurement`` / ``ath``) is NOT falsely
    banned.
  * Importing the Stage 25.5 production module is side-effect-free.
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
# Stage 25.5 file inventory
# ---------------------------------------------------------------------------


_STAGE25_1_PRODUCTION_FILENAMES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "constants.py",
        "errors.py",
        "models.py",
        "measurement_contracts.py",
        "input_reader.py",
        "stage25_manifest.py",
    }
)


_STAGE25_2_ADDED_FILENAMES: frozenset[str] = frozenset(
    {
        "migration_observation.py",
        "migration_measurement.py",
    }
)


_STAGE25_3_ADDED_FILENAMES: frozenset[str] = frozenset(
    {
        "price_observation.py",
        "price_window.py",
    }
)


_STAGE25_4_ADDED_FILENAMES: frozenset[str] = frozenset(
    {
        "ath_candidate.py",
    }
)


_STAGE25_5_ADDED_FILENAMES: frozenset[str] = frozenset(
    {
        "source_reconciliation.py",
    }
)


_STAGE25_6_ADDED_FILENAMES: frozenset[str] = frozenset(
    {
        "runner.py",
        "artifact_writer.py",
        "summary.py",
    }
)


_LOCKED_PRODUCTION_FILENAMES: frozenset[str] = (
    _STAGE25_1_PRODUCTION_FILENAMES
    | _STAGE25_2_ADDED_FILENAMES
    | _STAGE25_3_ADDED_FILENAMES
    | _STAGE25_4_ADDED_FILENAMES
    | _STAGE25_5_ADDED_FILENAMES
    | _STAGE25_6_ADDED_FILENAMES
)


# Files freshly introduced by Stage 25.5. Scoped boundary checks below
# inspect THIS subset so a regression in Stage 25.1 / 25.2 / 25.3 /
# 25.4 is not reported against Stage 25.5 and vice versa.
_STAGE25_5_NEW_MODULES: tuple[str, ...] = (
    "source_reconciliation.py",
)


_FORBIDDEN_FUTURE_FILENAMES: tuple[str, ...] = (
    # Later sub-stages (closure-audit / Stage 25.7+ surfaces).
    # Stage 25.5 does NOT ship a runner / writer / summary; the
    # locked inventory above includes Stage 25.6 graduated files
    # so the inventory check does not flag them as unexpected
    # files. The scoped Stage 25.5 boundary checks below still
    # only inspect ``source_reconciliation.py``.
    "stage25_runner.py",
    "evaluations_writer.py",
    "summary_writer.py",
    "csv_writer.py",
    "price_projector.py",
    "ath_reconciler.py",
    "ath_measurer.py",
    "ath_measurement.py",
    "source_reconciler.py",
    # Forbidden non-Stage-25 concerns.
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
    "x_api.py",
    "social.py",
)


# ---------------------------------------------------------------------------
# Forbidden import / call / module sets (mirror Stage 25.4)
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


# Stage 26 calibration / enforcement and Stage 27 X / social
# vocabulary. The forbidden-substring scanner refuses any new Stage
# 25.5 production identifier that carries one of these substrings.
_STAGE_26_27_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "calibration",
    "enforcement",
    "enforcer",
    "threshold_enforce",
    "ratchet",
    "tweet",
    "twitter",
    "subscriber_tier",
)


# Substrings naming Stage 25.6+ runner / writer surfaces that Stage
# 25.5 must NOT implement. Stage 25.5 ships the reconciler only -- the
# runner, artifact writer, and deterministic output paths are Stage
# 25.6+ surfaces.
_FORBIDDEN_DOMAIN_SUBSTRINGS_25_5: tuple[str, ...] = (
    "runner",
    "artifact_writer",
    "evaluations_writer",
    "summary_writer",
    "csv_writer",
    "write_text",
    "write_bytes",
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


def _iter_stage25_5_modules() -> list[Path]:
    return [
        STAGE25_ROOT / name
        for name in _STAGE25_5_NEW_MODULES
        if (STAGE25_ROOT / name).is_file()
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
# File inventory
# ---------------------------------------------------------------------------


def test_stage25_5_added_files_exist():
    for name in _STAGE25_5_ADDED_FILENAMES:
        path = STAGE25_ROOT / name
        assert path.is_file(), (
            f"Stage 25.5 requires production file {name}"
        )


def test_stage25_5_production_tree_matches_locked_inventory():
    files = {
        p.name
        for p in STAGE25_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    extra = files - _LOCKED_PRODUCTION_FILENAMES
    missing = _LOCKED_PRODUCTION_FILENAMES - files
    assert not extra, (
        f"Stage 25.5 production tree has unexpected files: "
        f"{sorted(extra)}"
    )
    assert not missing, (
        f"Stage 25.5 production tree is missing files: "
        f"{sorted(missing)}"
    )


def test_stage25_5_forbidden_future_files_do_not_exist():
    for name in _FORBIDDEN_FUTURE_FILENAMES:
        path = STAGE25_ROOT / name
        assert not path.exists(), (
            f"Stage 25.5 scope violation: {name} must not exist"
        )


# ---------------------------------------------------------------------------
# Top-level side-effect freedom (scoped to Stage 25.5 new modules)
# ---------------------------------------------------------------------------


def test_stage25_5_modules_have_side_effect_free_top_level():
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
    for py_file in _iter_stage25_5_modules():
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


def test_stage25_5_modules_have_no_forbidden_top_level_calls():
    for py_file in _iter_stage25_5_modules():
        names = _collect_top_level_call_names(_read_source(py_file))
        leaked = sorted(set(names) & set(_FORBIDDEN_TOP_LEVEL_CALL_NAMES))
        assert not leaked, (
            f"{py_file}: forbidden top-level call(s) {leaked}"
        )


# ---------------------------------------------------------------------------
# CLI surface absence
# ---------------------------------------------------------------------------


def test_stage25_5_modules_have_no_dunder_main_guard():
    for py_file in _iter_stage25_5_modules():
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


def test_stage25_5_modules_have_no_top_level_main_or_cli():
    forbidden_entrypoint_names: frozenset[str] = frozenset(
        {"main", "cli", "entrypoint"}
    )
    for py_file in _iter_stage25_5_modules():
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


def test_stage25_5_modules_do_not_import_cli_or_sleep_libs():
    for py_file in _iter_stage25_5_modules():
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
                    top
                    not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES
                ), (
                    f"{py_file}: forbidden CLI/sleep from-import "
                    f"{mod!r}"
                )


def test_stage25_5_modules_do_not_import_file_persistence_libs():
    for py_file in _iter_stage25_5_modules():
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
                    f"{py_file}: forbidden file-persistence "
                    f"from-import {mod!r}"
                )


# ---------------------------------------------------------------------------
# Import boundary
# ---------------------------------------------------------------------------


def test_stage25_5_modules_do_not_import_phoenix1():
    for py_file in _iter_stage25_5_modules():
        for target in _collect_full_targets(py_file):
            assert not target.startswith("phoenix1"), (
                f"{py_file}: forbidden phoenix1 import target "
                f"{target!r}"
            )
            assert not target.startswith("Phoenix1"), (
                f"{py_file}: forbidden Phoenix1 import target "
                f"{target!r}"
            )


def test_stage25_5_modules_do_not_import_prior_stage_production():
    for py_file in _iter_stage25_5_modules():
        for target in _collect_full_targets(py_file):
            for forbidden in (
                _FORBIDDEN_PRIOR_STAGE_PRODUCTION_PREFIXES
            ):
                assert not target.startswith(forbidden), (
                    f"{py_file}: forbidden prior-stage import "
                    f"{target!r}"
                )


def test_stage25_5_modules_do_not_import_phx2_runtime_layer():
    for py_file in _iter_stage25_5_modules():
        for target in _collect_full_targets(py_file):
            for forbidden in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{py_file}: forbidden PHX2 runtime-layer target "
                    f"{target!r}"
                )


def test_stage25_5_modules_do_not_import_runtime_module_patterns():
    for py_file in _iter_stage25_5_modules():
        for module in _collect_modules(py_file):
            lower = module.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{py_file}: forbidden module pattern "
                    f"{pattern!r} in import target {module!r}"
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


def test_stage25_5_modules_do_not_read_environ():
    for py_file in _iter_stage25_5_modules():
        assert not _module_reads_env_in_source(_read_source(py_file)), (
            f"{py_file}: forbidden env-read pattern. Stage 25 contract: "
            "no Stage 25 module may read the process environment."
        )


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


def test_stage25_5_modules_have_no_url_literal_in_source():
    for py_file in _iter_stage25_5_modules():
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


def test_stage25_5_modules_do_not_define_forbidden_vocabulary():
    for py_file in _iter_stage25_5_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE25_FORBIDDEN_VOCABULARY:
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains "
                    f"forbidden vocabulary substring {forbidden!r}"
                )


def test_stage25_5_modules_do_not_define_stage24_execution_fee_vocabulary():
    for py_file in _iter_stage25_5_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in (
                STAGE25_FORBIDDEN_STAGE24_EXECUTION_FEE_VOCABULARY
            ):
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains Stage "
                    f"24 execution-fee substring {forbidden!r}"
                )


def test_stage25_5_modules_do_not_define_forbidden_routing_token():
    for py_file in _iter_stage25_5_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE25_FORBIDDEN_ROUTING_TOKENS:
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains "
                    f"forbidden routing-token substring {forbidden!r}"
                )


def test_stage25_5_modules_do_not_define_stage26_27_vocabulary():
    """Stage 25.5 production must not introduce Stage 26 calibration /
    enforcement or Stage 27 X / social vocabulary.
    """
    for py_file in _iter_stage25_5_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in _STAGE_26_27_FORBIDDEN_SUBSTRINGS:
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains "
                    f"Stage 26/27 substring {forbidden!r}"
                )


def test_stage25_5_modules_do_not_define_runner_or_writer_vocabulary():
    """Stage 25.5 must NOT ship a runner, artifact writer, or any
    deterministic output writer.

    The reconciler emits in-memory ``Stage25SourceReconciliation`` /
    ``Stage25ATHMeasurement`` records that a future Stage 25.6 runner /
    writer consumes; Stage 25.5 itself ships NO writer.
    """
    for py_file in _iter_stage25_5_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in _FORBIDDEN_DOMAIN_SUBSTRINGS_25_5:
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains "
                    f"forbidden Stage 25.6+ domain substring "
                    f"{forbidden!r}"
                )


# ---------------------------------------------------------------------------
# Stage 25.5 vocabulary preserved (reconciliation / source / confidence etc.)
# ---------------------------------------------------------------------------


def test_stage25_5_vocabulary_is_legal_substring():
    """Sanity: Stage 25.5's own vocabulary must remain legal
    identifier-position substrings.

    The Stage 25.5 spec explicitly warns against brittle substring
    checks that falsely reject legitimate Stage 25.5 vocabulary like
    ``reconciliation`` / ``source`` / ``confidence`` /
    ``measurement`` / ``ath`` / ``peak`` / ``candidate`` / ``price``.
    """
    legal_substrings = (
        "reconciliation",
        "source",
        "confidence",
        "measurement",
        "ath",
        "ath_measurement",
        "peak",
        "candidate",
        "price",
        "window",
        "observation",
        "migration",
        "swap_replay",
        "disagreement",
        "agreement",
    )
    forbidden_set = (
        set(STAGE25_FORBIDDEN_VOCABULARY)
        | set(STAGE25_FORBIDDEN_STAGE24_EXECUTION_FEE_VOCABULARY)
        | set(STAGE25_FORBIDDEN_ROUTING_TOKENS)
        | set(_STAGE_26_27_FORBIDDEN_SUBSTRINGS)
        | set(_FORBIDDEN_DOMAIN_SUBSTRINGS_25_5)
    )
    for word in legal_substrings:
        assert word not in forbidden_set, (
            f"Stage 25.5 vocabulary word {word!r} must remain "
            "a legal identifier-position substring"
        )


# ---------------------------------------------------------------------------
# No-write discipline
# ---------------------------------------------------------------------------


def test_stage25_5_modules_do_not_call_write_text_or_write_bytes():
    forbidden_attrs: frozenset[str] = frozenset(
        {"write_text", "write_bytes"}
    )
    for py_file in _iter_stage25_5_modules():
        tree = ast.parse(_read_source(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_attrs, (
                    f"{py_file}: forbidden attribute reference "
                    f"{node.attr!r}; Stage 25.5 has no artifact writer"
                )


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


def test_stage25_5_modules_import_cleanly():
    """Each Stage 25.5 production module must import without side effects."""
    import importlib

    expected = {
        "PHX2.stage25.source_reconciliation",
    }
    for name in expected:
        module = importlib.import_module(name)
        assert module is not None
