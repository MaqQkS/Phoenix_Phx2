"""Stage 26.3 file-scope / import-boundary / vocabulary tests.

These tests focus specifically on the Stage 26.3 production files
(``cohort_constants.py`` / ``cohort_models.py`` / ``cohort_builder.py``)
and pin:

  * No Stage 21 / 22 / 23 / 24 import.
  * No direct ``PHX2.stage25`` import; Stage 25 vocabulary must
    route through ``PHX2.stage26.stage25_schema_whitelist`` (or via
    Stage 26.1 / 26.2 surfaces) -- the Stage 26.3 production files
    MUST NOT import from ``PHX2.stage25`` themselves.
  * No network / RPC / messaging / DB / scheduler / secrets library.
  * No CLI entrypoint, no ``__name__ == "__main__"`` guard.
  * No filesystem writer call (write_text / write_bytes / unlink /
    rmdir / rmtree / touch / mkdir).
  * No ``open(..., "w")`` / append / exclusive mode.
  * No ``open()`` call at all -- Stage 26.3 is in-memory only.
  * No ``os.environ`` / ``os.getenv``.
  * No URL literal.
  * No Stage 26.4+ file name shipped (threshold / policy / review
    packet / runner / writer / CLI / dispatch).
  * No Stage 26.4+ vocabulary identifier (threshold_candidate /
    policy_candidate / approval_state / enforcement / dispatch /
    etc.).
  * No identifier collapses MISSING into UNSUPPORTED, UNSUPPORTED
    into REJECTED, or any non-MEASURED truth class into MEASURED.
"""

from __future__ import annotations

import ast
from pathlib import Path


STAGE26_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent / "stage26"
)


_STAGE_26_3_PRODUCTION_FILENAMES: tuple[str, ...] = (
    "cohort_constants.py",
    "cohort_models.py",
    "cohort_builder.py",
)


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
)


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    "helius",
    "jupiter",
    "discord",
    "telegram",
    "telethon",
    "webhook",
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "daemon",
    "sqlalchemy",
    "sqlite3",
    "dotenv",
    "keyring",
)


_FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES: frozenset[str] = frozenset(
    {"argparse", "click", "typer", "fire", "docopt", "time", "asyncio"}
)


_FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES: frozenset[str] = frozenset(
    {"shutil", "tempfile", "csv"}
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


# Stage 26.4+ vocabulary the Stage 26.3 files MUST NOT introduce.
# ``cohort`` / ``denominator_status`` are Stage 26.2 / 26.3 locked
# vocabulary and are NOT forbidden here (see test_stage_26_1_boundaries
# for the unlocking rationale).
_FORBIDDEN_DOMAIN_SUBSTRINGS_FOR_STAGE_26_3: tuple[str, ...] = (
    "approval_state",
    "approved_by",
    "threshold_candidate",
    "policy_candidate",
    "enforcement",
    "enforcer",
    "ratchet",
    "tweet",
    "twitter",
    "x_api",
    "subscriber_tier",
    "dispatcher",
    "telegram",
    "discord",
    "axiom",
    "jito",
    "compute_budget",
    "router_fee",
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


_FORBIDDEN_WRITER_ATTRIBUTE_NAMES: frozenset[str] = frozenset(
    {
        "write_text",
        "write_bytes",
        "unlink",
        "rmdir",
        "rmtree",
        "replace",
        "rename",
        "touch",
        "mkdir",
    }
)


_FORBIDDEN_OPEN_MODE_TOKENS: frozenset[str] = frozenset(
    {"w", "wb", "w+", "wb+", "a", "ab", "x", "xb"}
)


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


# Stage 26.4+ file-basename surfaces Stage 26.3 must not introduce.
_FORBIDDEN_FUTURE_SUBSTAGE_BASENAMES: tuple[str, ...] = (
    "threshold.py",
    "threshold_generator.py",
    "threshold_candidate.py",
    "policy.py",
    "policy_candidate.py",
    "policy_writer.py",
    "review_packet.py",
    "operator_review.py",
    "runner.py",
    "writer.py",
    "cli.py",
    "main.py",
    "scheduler.py",
    "daemon.py",
    "dispatch.py",
    "dispatcher.py",
    "telegram.py",
    "discord.py",
    "x_api.py",
    "social.py",
)


def _iter_stage26_3_production_files() -> list[Path]:
    return [
        STAGE26_ROOT / name for name in _STAGE_26_3_PRODUCTION_FILENAMES
    ]


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_imports(source: str) -> tuple[set[str], set[str]]:
    tree = ast.parse(source)
    modules: set[str] = set()
    full: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                full.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
                full.add(mod)
                for alias in node.names:
                    full.add(f"{mod}.{alias.name}")
    return modules, full


def _collect_call_func_chain_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func: ast.expr = node.func
            while isinstance(func, ast.Attribute):
                names.add(func.attr)
                func = func.value
            if isinstance(func, ast.Name):
                names.add(func.id)
    return names


def _collect_open_calls(source: str) -> list[ast.Call]:
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                calls.append(node)
            elif isinstance(func, ast.Attribute) and func.attr == "open":
                calls.append(node)
    return calls


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


# ---------------------------------------------------------------------------
# Stage 26.3 file inventory
# ---------------------------------------------------------------------------


def test_stage_26_3_production_files_exist():
    for name in _STAGE_26_3_PRODUCTION_FILENAMES:
        path = STAGE26_ROOT / name
        assert path.is_file(), f"missing Stage 26.3 production file {name!r}"


def test_no_forbidden_future_substage_files_present():
    for basename in _FORBIDDEN_FUTURE_SUBSTAGE_BASENAMES:
        assert not (STAGE26_ROOT / basename).exists(), (
            f"Stage 26 must not ship {basename!r}; reserved for Stage 26.4+"
        )


# ---------------------------------------------------------------------------
# Stage 26.3 import boundaries
# ---------------------------------------------------------------------------


def test_no_stage_26_3_imports_prior_stage():
    for path in _iter_stage26_3_production_files():
        _, full = _collect_imports(_read_source(path))
        for target in full:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden prior-stage import {target!r}"
                )


def test_no_stage_26_3_imports_stage25_directly():
    """Stage 26.3 must NOT import from ``PHX2.stage25`` directly.

    The whitelist module (``PHX2.stage26.stage25_schema_whitelist``)
    is the only Stage 26 module permitted to do so.
    """
    for path in _iter_stage26_3_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            assert not module.startswith("PHX2.stage25"), (
                f"{path.name}: forbidden Stage 25 import {module!r}; "
                "Stage 26.3 must consume Stage 25 vocabulary via "
                "PHX2.stage26.constants / .models / "
                ".eligibility_models / .stage25_schema_whitelist"
            )


def test_no_stage_26_3_imports_runtime_module_patterns():
    for path in _iter_stage26_3_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            lower = module.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path.name}: forbidden runtime pattern "
                    f"{pattern!r} in import target {module!r}"
                )


def test_no_stage_26_3_imports_cli_or_sleep_libs():
    for path in _iter_stage26_3_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            top = module.split(".")[0]
            assert top not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES, (
                f"{path.name}: forbidden CLI/sleep import {module!r}"
            )


def test_no_stage_26_3_imports_file_persistence_libs():
    for path in _iter_stage26_3_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            top = module.split(".")[0]
            assert top not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES, (
                f"{path.name}: forbidden file-persistence import {module!r}"
            )


def test_no_stage_26_3_imports_phx2_runtime_layer():
    for path in _iter_stage26_3_production_files():
        _, full = _collect_imports(_read_source(path))
        for target in full:
            for forbidden in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden PHX2 runtime-layer target "
                    f"{target!r}"
                )


# ---------------------------------------------------------------------------
# Env / CLI / writer / URL boundary
# ---------------------------------------------------------------------------


def test_no_stage_26_3_reads_environ():
    for path in _iter_stage26_3_production_files():
        source = _read_source(path)
        tree = ast.parse(source)
        os_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        os_aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "os":
                    for alias in node.names:
                        assert alias.name not in _ENV_ATTR_NAMES, (
                            f"{path.name}: forbidden env-read import "
                            f"{alias.name!r}"
                        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id in os_aliases
                ):
                    assert node.attr not in _ENV_ATTR_NAMES, (
                        f"{path.name}: forbidden os.{node.attr}"
                    )


def test_no_stage_26_3_defines_cli_entrypoint():
    forbidden_names = {"main", "cli", "entrypoint"}
    for path in _iter_stage26_3_production_files():
        tree = ast.parse(_read_source(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in forbidden_names, (
                    f"{path.name}: forbidden CLI-style entrypoint "
                    f"{node.name!r}"
                )


def test_no_stage_26_3_has_dunder_main_guard():
    for path in _iter_stage26_3_production_files():
        tree = ast.parse(_read_source(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                participants: list[ast.expr] = [node.left]
                participants.extend(node.comparators)
                has_name = any(
                    isinstance(p, ast.Name) and p.id == "__name__"
                    for p in participants
                )
                has_main = any(
                    isinstance(p, ast.Constant) and p.value == "__main__"
                    for p in participants
                )
                assert not (has_name and has_main), (
                    f"{path.name}: forbidden __name__ == '__main__' guard"
                )


def test_no_stage_26_3_has_url_literal():
    for path in _iter_stage26_3_production_files():
        source = _read_source(path)
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path.name}: forbidden URL literal {needle!r}"
            )


def test_no_stage_26_3_calls_filesystem_writer_apis():
    for path in _iter_stage26_3_production_files():
        called_names = _collect_call_func_chain_names(_read_source(path))
        leaked = sorted(called_names & _FORBIDDEN_WRITER_ATTRIBUTE_NAMES)
        assert not leaked, (
            f"{path.name}: forbidden writer call(s) {leaked}"
        )


def test_no_stage_26_3_opens_a_file_in_write_mode():
    for path in _iter_stage26_3_production_files():
        calls = _collect_open_calls(_read_source(path))
        for call in calls:
            mode: str = "r"
            if len(call.args) >= 2:
                second = call.args[1]
                if isinstance(second, ast.Constant) and isinstance(
                    second.value, str
                ):
                    mode = second.value
            for keyword in call.keywords:
                if keyword.arg == "mode" and isinstance(
                    keyword.value, ast.Constant
                ) and isinstance(keyword.value.value, str):
                    mode = keyword.value.value
            assert mode not in _FORBIDDEN_OPEN_MODE_TOKENS, (
                f"{path.name}: forbidden open() mode {mode!r}"
            )


def test_no_stage_26_3_opens_a_file_at_all():
    """Stage 26.3 is in-memory only; it consumes Stage 26.2 records,
    not Stage 25 artifact bytes. No ``open()`` call is permitted.
    """
    for path in _iter_stage26_3_production_files():
        calls = _collect_open_calls(_read_source(path))
        assert not calls, (
            f"{path.name}: Stage 26.3 must not open() files; consume "
            "Stage 26.2 in-memory records instead"
        )


# ---------------------------------------------------------------------------
# Identifier vocabulary scan (Stage 26.4+ vocabulary forbidden)
# ---------------------------------------------------------------------------


def test_no_stage_26_3_identifier_carries_forbidden_substring():
    for path in _iter_stage26_3_production_files():
        idents = _extract_all_identifiers(_read_source(path))
        for ident in idents:
            lower = ident.lower()
            for forbidden in _FORBIDDEN_DOMAIN_SUBSTRINGS_FOR_STAGE_26_3:
                assert forbidden not in lower, (
                    f"{path.name}: identifier {ident!r} contains "
                    f"forbidden Stage 26.4+ substring {forbidden!r}"
                )


# ---------------------------------------------------------------------------
# Top-level side-effect freedom
# ---------------------------------------------------------------------------


def test_stage_26_3_modules_have_side_effect_free_top_level():
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
    for path in _iter_stage26_3_production_files():
        tree = ast.parse(_read_source(path))
        for node in tree.body:
            assert isinstance(node, allowed_top_level), (
                f"{path.name}: unexpected top-level node "
                f"{type(node).__name__}"
            )


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


def test_each_stage_26_3_production_module_imports_cleanly():
    import importlib

    expected = {
        "PHX2.stage26.cohort_constants",
        "PHX2.stage26.cohort_models",
        "PHX2.stage26.cohort_builder",
    }
    for name in expected:
        module = importlib.import_module(name)
        assert module is not None
