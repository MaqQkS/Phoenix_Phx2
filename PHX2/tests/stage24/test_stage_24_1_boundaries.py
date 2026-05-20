"""Stage 24.1 file-scope / import-boundary / vocabulary tests.

Pins the 24.1 scope at the file and identifier level:

  * The Stage 24 production tree contains EXACTLY the locked
    seven files (``__init__.py``, ``constants.py``, ``errors.py``,
    ``models.py``, ``decoder_contracts.py``, ``input_reader.py``,
    ``stage24_manifest.py``).
  * Forbidden 24.1 production filenames (later-stage decoders,
    runners, artifact writers, alert dispatchers, scheduler
    files) do not exist.
  * No production module imports Stage 21 / Stage 22 / Stage 23
    production modules.
  * No production module imports a Birdeye / Dexscreener /
    Migration / X / social / Phoenix1 module.
  * No production module imports Discord / Telegram /
    public-routing modules.
  * No production module imports a network / RPC / messaging /
    DB / scheduler / secrets-management library.
  * No production module reads ``os.environ`` / ``os.getenv``.
  * No production module's identifier vocabulary introduces a
    Stage 24-forbidden substring.
  * No production identifier carries the word-level forbidden
    ``ath`` token (Stage 25 ATH concept).
  * Stage 24's own vocabulary -- ``axiom`` / ``jito`` /
    ``priority_fee`` / ``compute_budget`` / ``execution_quality``
    -- is NOT falsely banned.
  * No production module writes to disk (no ``write_text`` /
    ``write_bytes``).
  * No production module contains a URL literal or webhook host
    literal.
  * No production module contains a top-level call to a
    forbidden I/O / sleep / persistence callable.
  * Importing every production module is side-effect-free at
    the top level.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from PHX2.stage24.constants import (
    STAGE24_FORBIDDEN_ROUTING_TOKENS,
    STAGE24_FORBIDDEN_VOCABULARY,
    STAGE24_FORBIDDEN_VOCABULARY_WORDS,
)


STAGE24_ROOT: Path = Path(__file__).parent.parent.parent / "stage24"


# ---------------------------------------------------------------------------
# Locked production / forbidden file sets
# ---------------------------------------------------------------------------


_LOCKED_PRODUCTION_FILENAMES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "constants.py",
        "errors.py",
        "models.py",
        "decoder_contracts.py",
        "input_reader.py",
        "stage24_manifest.py",
        # Stage 24.2 decoder pair (admitted in 24.2; see
        # test_stage_24_2_boundaries.py for the 24.2 file-scope
        # invariants).
        "compute_budget.py",
        "priority_fee.py",
        # Stage 24.3 Jito tip decoder (admitted in 24.3; see
        # test_stage_24_3_boundaries.py for the 24.3 file-scope
        # invariants).
        "jito_tip.py",
    }
)


# Stage 24.1 ``pathlib`` is allowed in the modules that take an
# operator-supplied path. Every other Stage 24 production module
# is forbidden from importing ``pathlib``.
_PATHLIB_ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "input_reader.py",
        "stage24_manifest.py",
    }
)


_FORBIDDEN_PRODUCTION_FILENAMES: tuple[str, ...] = (
    # Reserved-but-not-used decoder filenames (later sub-stages).
    # ``compute_budget.py`` / ``priority_fee.py`` were forbidden at
    # 24.1; they were admitted at 24.2 and now appear in
    # ``_LOCKED_PRODUCTION_FILENAMES``. ``jito_tip.py`` was
    # forbidden at 24.1-24.2; it was admitted at 24.3 and now
    # appears in ``_LOCKED_PRODUCTION_FILENAMES`` as well.
    "router_fee.py",
    "execution_quality.py",
    # Reserved-but-not-used runner / writer filenames.
    "runner.py",
    "artifact_writer.py",
    "stage24_runner.py",
    "evaluations_writer.py",
    "summary_writer.py",
    "csv_writer.py",
    # Closure / handoff docs not yet written.
    "STAGE_24_CLOSURE_AUDIT.md",
    "STAGE_25_HANDOFF.md",
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
    "ath.py",
    "x_api.py",
    "social.py",
)


_FORBIDDEN_PRODUCTION_SUBDIRS: tuple[str, ...] = (
    "decoders",
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


# Stage 24 forbidden runtime module patterns. Mirrors the Stage 23
# discipline but intentionally OMITS ``axiom`` / ``jito`` /
# ``priority_fee`` / ``compute_budget`` / ``execution_quality``
# because those are the Stage 24 vocabulary. Stage 24.1 does not
# import any module containing those substrings in any case (the
# decoders are local to ``PHX2.stage24`` and arrive in 24.2+).
_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
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
        for p in STAGE24_ROOT.rglob("*.py")
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


def test_stage24_root_directory_exists():
    assert STAGE24_ROOT.is_dir(), (
        f"Stage 24 production root {STAGE24_ROOT} must exist"
    )


def test_locked_production_files_all_exist():
    for name in _LOCKED_PRODUCTION_FILENAMES:
        path = STAGE24_ROOT / name
        assert path.is_file(), (
            f"Stage 24.1 requires production file {name}"
        )


def test_no_extra_production_files_exist():
    files = {
        p.name
        for p in STAGE24_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    extra = files - _LOCKED_PRODUCTION_FILENAMES
    assert not extra, (
        f"Stage 24.1 production tree has unexpected files: "
        f"{sorted(extra)}"
    )


def test_forbidden_production_filenames_do_not_exist():
    for name in _FORBIDDEN_PRODUCTION_FILENAMES:
        path = STAGE24_ROOT / name
        assert not path.exists(), (
            f"Stage 24.1 scope violation: {name} must not exist"
        )


def test_no_forbidden_production_subdirs():
    for name in _FORBIDDEN_PRODUCTION_SUBDIRS:
        path = STAGE24_ROOT / name
        assert not path.exists(), (
            f"Stage 24.1 scope violation: subdirectory {name!r} must not "
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
                        top not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES
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
# Import boundary -- no prior Stage / Phoenix1 / runtime imports
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


def test_no_stage24_module_reads_environ():
    for py_file in _iter_production_modules():
        assert not _module_reads_env_in_source(_read_source(py_file)), (
            f"{py_file}: forbidden env-read pattern. Stage 24 contract: "
            "no Stage 24 module may read the process environment."
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


_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _split_identifier_into_words(identifier: str) -> list[str]:
    """Split an identifier into lowercased word-parts.

    Splits on underscores and lowercase->uppercase boundaries.
    ``"someAthValue_thing"`` -> ``["some", "ath", "value", "thing"]``.
    ``"path"`` -> ``["path"]``.
    ``"_INPUT_CONCEPT_ALIASES"`` -> ``["input", "concept", "aliases"]``.
    """
    underscore_parts = identifier.split("_")
    words: list[str] = []
    for raw in underscore_parts:
        if raw == "":
            continue
        for piece in _CASE_BOUNDARY_RE.split(raw):
            if piece != "":
                words.append(piece.lower())
    return words


def test_no_production_identifier_contains_forbidden_vocabulary():
    """Substring scan: every identifier in every Stage 24 production
    module must avoid each entry of ``STAGE24_FORBIDDEN_VOCABULARY``.
    The scan operates on identifier-position names extracted from
    the AST; string literals (including docstrings and the locked
    forbidden-vocabulary tuple in ``constants.py``) are NOT
    scanned.
    """
    for py_file in _iter_production_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE24_FORBIDDEN_VOCABULARY:
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains forbidden "
                    f"vocabulary substring {forbidden!r}"
                )


def test_no_production_identifier_carries_word_level_forbidden_token():
    """Word-level scan: every identifier-part (split by ``_`` and
    case-boundary) must avoid each entry of
    ``STAGE24_FORBIDDEN_VOCABULARY_WORDS``. This handles short
    ambiguous tokens like ``ath`` that would otherwise match safe
    substrings (``path``, ``math``, ``hashlib``).
    """
    for py_file in _iter_production_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            words = _split_identifier_into_words(ident)
            for forbidden in STAGE24_FORBIDDEN_VOCABULARY_WORDS:
                assert forbidden not in words, (
                    f"{py_file}: identifier {ident!r} carries forbidden "
                    f"word-level token {forbidden!r}"
                )


def test_no_production_identifier_contains_forbidden_routing_token():
    """Substring scan: every identifier must avoid each
    ``STAGE24_FORBIDDEN_ROUTING_TOKENS`` token.
    """
    for py_file in _iter_production_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE24_FORBIDDEN_ROUTING_TOKENS:
                assert forbidden not in lower, (
                    f"{py_file}: identifier {ident!r} contains forbidden "
                    f"routing-token substring {forbidden!r}"
                )


def test_stage24_vocabulary_is_not_falsely_banned():
    """Stage 24's own vocabulary (``axiom``, ``jito``, ``priority_fee``,
    ``compute_budget``, ``execution_quality``) MUST NOT be on the
    Stage 24 forbidden vocabulary list. These are the stage's
    domain concepts and must remain usable as identifier parts.
    """
    forbidden = set(STAGE24_FORBIDDEN_VOCABULARY)
    for stage24_word in (
        "axiom",
        "jito",
        "priority_fee",
        "compute_budget",
        "execution_quality",
    ):
        assert stage24_word not in forbidden, (
            f"Stage 24 vocabulary word {stage24_word!r} must not be on "
            "the forbidden list"
        )


# ---------------------------------------------------------------------------
# No-write discipline
# ---------------------------------------------------------------------------


def test_no_production_module_calls_write_text_or_write_bytes():
    """Stage 24.1 production code MUST NOT write to disk.

    The Stage 24.6 artifact writer is the future home for any
    on-disk writing. 24.1 only reads inputs and hashes files;
    it does not produce any output file.
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
                    f"{node.attr!r}; Stage 24.1 has no artifact writer"
                )


# ---------------------------------------------------------------------------
# Negative fixtures (collector sanity)
# ---------------------------------------------------------------------------


def _has_forbidden_prior_stage(source: str) -> bool:
    _, full_targets = _collect_import_targets_from_source(source)
    for target in full_targets:
        for forbidden in _FORBIDDEN_PRIOR_STAGE_PRODUCTION_PREFIXES:
            if target.startswith(forbidden):
                return True
    return False


def test_collector_catches_phx2_stage23_import():
    source = "from PHX2.stage23.constants import STAGE23_VERSION\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_phx2_stage22_import():
    source = "from PHX2.stage22.constants import STAGE22_VERSION\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_dunder_import_literal():
    source = "__import__('PHX2.stage23')\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_does_not_catch_docstring_mention():
    source = (
        '"""Docstring mentions PHX2.stage23 but does not import it."""\n'
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


def test_word_splitter_handles_pathlib_safely():
    # ``ath`` must not match inside ``path`` / ``pathlib`` / ``Path``.
    for ident in ("path", "pathlib", "Path", "_require_path_is_existing_file"):
        words = _split_identifier_into_words(ident)
        assert "ath" not in words, (
            f"word splitter incorrectly produced 'ath' from {ident!r}"
        )


def test_word_splitter_catches_ath_when_present():
    # A hypothetical identifier with ``ath`` as a discrete word
    # part must trigger the word-level scanner.
    words = _split_identifier_into_words("token_ath_value")
    assert "ath" in words
    words = _split_identifier_into_words("someAthValue")
    assert "ath" in words
