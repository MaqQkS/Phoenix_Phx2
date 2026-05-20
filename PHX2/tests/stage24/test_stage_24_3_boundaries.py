"""Stage 24.3 file-scope / import-boundary / vocabulary tests.

Pins the 24.3 scope at the file and identifier level:

  * The Stage 24 production tree contains EXACTLY the locked
    ten files: the seven 24.1 files plus ``compute_budget.py``
    (24.2), ``priority_fee.py`` (24.2), and the new
    ``jito_tip.py`` (24.3).
  * Later Stage 24 decoder / runner / writer / closure files
    do NOT exist yet (24.4-24.7).
  * ``jito_tip.py`` does not import Stage 21 / Stage 22 /
    Stage 23 / PHX2 runtime / network / DB / dispatch /
    scheduler / secrets-management / CLI / file-persistence
    libraries, and does not read ``os.environ``.
  * No identifier defined in ``jito_tip.py`` carries a Stage 24-
    forbidden vocabulary substring (or the word-level ``ath``
    token).
  * No identifier carries a forbidden routing token.
  * No URL / webhook host literal appears in ``jito_tip.py``.
  * ``jito_tip.py`` may use ``base64`` / ``binascii`` from
    stdlib for instruction-byte decoding.
  * Top-level scope of ``jito_tip.py`` is side-effect-free.
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
# Locked file sets
# ---------------------------------------------------------------------------


_STAGE_24_3_APPROVED_PRODUCTION_FILENAMES: frozenset[str] = frozenset(
    {
        # Stage 24.1 foundation
        "__init__.py",
        "constants.py",
        "errors.py",
        "models.py",
        "decoder_contracts.py",
        "input_reader.py",
        "stage24_manifest.py",
        # Stage 24.2 decoders
        "compute_budget.py",
        "priority_fee.py",
        # Stage 24.3 decoder
        "jito_tip.py",
        # Stage 24.4 router-fee candidate scaffold (admitted in
        # 24.4; the 24.3 file-scope invariants are extended here
        # so the 24.3 boundary scanner stays accurate after 24.4
        # lands).
        "router_fee.py",
        # Stage 24.6 runner / writer / quality surface (admitted
        # in 24.6; the 24.3 file-scope invariants are extended
        # here so the 24.3 boundary scanner stays accurate after
        # 24.6 lands).
        "execution_quality.py",
        "runner.py",
        "artifact_writer.py",
    }
)


_STAGE_24_3_NEW_PRODUCTION_FILENAMES: tuple[str, ...] = (
    "jito_tip.py",
)


_FORBIDDEN_LATER_STAGE_PRODUCTION_FILENAMES: tuple[str, ...] = (
    # Later-stage decoders / runners / writers. ``router_fee.py``
    # was forbidden at 24.3 but is admitted at 24.4 and now
    # appears in ``_STAGE_24_3_APPROVED_PRODUCTION_FILENAMES``
    # instead. ``execution_quality.py`` / ``runner.py`` /
    # ``artifact_writer.py`` were forbidden at 24.3-24.5 but are
    # admitted at 24.6 and now appear in
    # ``_STAGE_24_3_APPROVED_PRODUCTION_FILENAMES``.
    "stage24_runner.py",
    "evaluations_writer.py",
    "summary_writer.py",
    "csv_writer.py",
    # Stage 24.7 closure docs
    "STAGE_24_CLOSURE_AUDIT.md",
    "STAGE_25_HANDOFF.md",
    # Scheduler / daemon (forever forbidden in Stage 24)
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
    # Wrong-stage primitives
    "birdeye.py",
    "dexscreener.py",
    "ath.py",
    "x_api.py",
    "social.py",
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


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
)


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_new_modules() -> list[Path]:
    return [
        STAGE24_ROOT / name
        for name in _STAGE_24_3_NEW_PRODUCTION_FILENAMES
    ]


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
    return modules


def _collect_full_import_targets(source: str) -> set[str]:
    tree = ast.parse(source)
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                targets.add(mod)
                for alias in node.names:
                    targets.add(f"{mod}.{alias.name}")
    return targets


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
    underscore_parts = identifier.split("_")
    words: list[str] = []
    for raw in underscore_parts:
        if raw == "":
            continue
        for piece in _CASE_BOUNDARY_RE.split(raw):
            if piece != "":
                words.append(piece.lower())
    return words


# ---------------------------------------------------------------------------
# File scope
# ---------------------------------------------------------------------------


def test_only_approved_stage_24_3_production_files_exist():
    files = {
        p.name
        for p in STAGE24_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    unexpected = files - _STAGE_24_3_APPROVED_PRODUCTION_FILENAMES
    assert not unexpected, (
        "Stage 24.3 production tree has unexpected files: "
        f"{sorted(unexpected)}"
    )


def test_new_stage_24_3_decoder_exists():
    for name in _STAGE_24_3_NEW_PRODUCTION_FILENAMES:
        path = STAGE24_ROOT / name
        assert path.is_file(), (
            f"Stage 24.3 requires production file {name}"
        )


def test_later_stage_24_files_do_not_exist():
    for name in _FORBIDDEN_LATER_STAGE_PRODUCTION_FILENAMES:
        path = STAGE24_ROOT / name
        assert not path.exists(), (
            f"Stage 24.3 scope violation: {name} must not exist yet"
        )


def test_execution_quality_module_is_admitted_after_stage_24_6():
    """``execution_quality.py`` landed at Stage 24.6 and is admitted
    by the Stage 24.3 boundary scanner from that point onward.
    """
    assert (STAGE24_ROOT / "execution_quality.py").is_file()


def test_runner_module_is_admitted_after_stage_24_6():
    assert (STAGE24_ROOT / "runner.py").is_file()


def test_artifact_writer_module_is_admitted_after_stage_24_6():
    assert (STAGE24_ROOT / "artifact_writer.py").is_file()


def test_no_later_stage_subdirectories_exist():
    forbidden_subdirs = (
        "decoders",
        "runners",
        "writers",
        "transports",
        "adapters",
        "social",
    )
    for name in forbidden_subdirs:
        path = STAGE24_ROOT / name
        assert not path.exists(), (
            f"Stage 24.3 scope violation: subdirectory {name!r} must not "
            "exist"
        )


# ---------------------------------------------------------------------------
# Import boundary
# ---------------------------------------------------------------------------


def test_new_modules_do_not_import_prior_stage_production():
    for path in _iter_new_modules():
        for target in _collect_full_import_targets(_read_source(path)):
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PRODUCTION_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import {target!r}"
                )


def test_new_modules_do_not_import_phx2_runtime_layers():
    for path in _iter_new_modules():
        for target in _collect_full_import_targets(_read_source(path)):
            for forbidden in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden PHX2 runtime-layer target "
                    f"{target!r}"
                )


def test_new_modules_do_not_import_phoenix1():
    for path in _iter_new_modules():
        for target in _collect_full_import_targets(_read_source(path)):
            assert not target.lower().startswith("phoenix1"), (
                f"{path}: forbidden phoenix1 import target {target!r}"
            )


def test_new_modules_do_not_import_forbidden_runtime_modules():
    for path in _iter_new_modules():
        for module in _collect_modules(_read_source(path)):
            lower = module.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden module pattern {pattern!r} in "
                    f"import target {module!r}"
                )


def test_new_modules_do_not_import_cli_or_sleep_libs():
    for path in _iter_new_modules():
        tree = ast.parse(_read_source(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert (
                        top
                        not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES
                    ), (
                        f"{path}: forbidden CLI/sleep import "
                        f"{alias.name!r}"
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0]
                assert (
                    top not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES
                ), (
                    f"{path}: forbidden CLI/sleep from-import {mod!r}"
                )


def test_new_modules_do_not_import_file_persistence_libs():
    for path in _iter_new_modules():
        tree = ast.parse(_read_source(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert (
                        top
                        not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES
                    ), (
                        f"{path}: forbidden file-persistence import "
                        f"{alias.name!r}"
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0]
                assert (
                    top
                    not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES
                ), (
                    f"{path}: forbidden file-persistence from-import "
                    f"{mod!r}"
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


def test_new_modules_do_not_read_environ():
    for path in _iter_new_modules():
        assert not _module_reads_env_in_source(_read_source(path)), (
            f"{path}: forbidden env-read pattern. Stage 24 contract: "
            "no Stage 24 module may read the process environment."
        )


# ---------------------------------------------------------------------------
# Top-level side-effect freedom
# ---------------------------------------------------------------------------


def test_new_modules_have_side_effect_free_top_level():
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
    for path in _iter_new_modules():
        tree = ast.parse(_read_source(path))
        for node in tree.body:
            assert isinstance(node, allowed_top_level), (
                f"{path}: unexpected top-level node {type(node).__name__}"
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


def test_new_modules_have_no_forbidden_top_level_calls():
    for path in _iter_new_modules():
        names = _collect_top_level_call_names(_read_source(path))
        leaked = sorted(set(names) & set(_FORBIDDEN_TOP_LEVEL_CALL_NAMES))
        assert not leaked, (
            f"{path}: forbidden top-level call(s) {leaked}"
        )


def test_new_modules_have_no_dunder_main_guard():
    for path in _iter_new_modules():
        tree = ast.parse(_read_source(path))
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
                    f"{path}: forbidden __name__ == '__main__' guard"
                )


def test_new_modules_have_no_main_or_cli_entrypoint():
    forbidden_entrypoint_names: frozenset[str] = frozenset(
        {"main", "cli", "entrypoint"}
    )
    for path in _iter_new_modules():
        tree = ast.parse(_read_source(path))
        for node in tree.body:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                assert node.name not in forbidden_entrypoint_names, (
                    f"{path}: forbidden CLI-style entrypoint "
                    f"function {node.name!r}"
                )


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


def test_new_modules_have_no_url_literals():
    for path in _iter_new_modules():
        source = _read_source(path)
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL literal {needle!r} in source"
            )


def test_new_modules_do_not_call_write_text_or_write_bytes():
    """Stage 24.3 has no artifact writer; that lands in Stage 24.6."""
    forbidden_attrs: frozenset[str] = frozenset(
        {"write_text", "write_bytes"}
    )
    for path in _iter_new_modules():
        tree = ast.parse(_read_source(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_attrs, (
                    f"{path}: forbidden attribute reference "
                    f"{node.attr!r}; Stage 24.3 has no artifact writer"
                )


# ---------------------------------------------------------------------------
# Identifier vocabulary scan
# ---------------------------------------------------------------------------


def test_new_module_identifiers_avoid_forbidden_vocabulary():
    for path in _iter_new_modules():
        idents = _extract_all_identifiers(_read_source(path))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE24_FORBIDDEN_VOCABULARY:
                assert forbidden not in lower, (
                    f"{path}: identifier {ident!r} contains forbidden "
                    f"vocabulary substring {forbidden!r}"
                )


def test_new_module_identifiers_avoid_word_level_ath():
    for path in _iter_new_modules():
        idents = _extract_all_identifiers(_read_source(path))
        for ident in idents:
            words = _split_identifier_into_words(ident)
            for forbidden in STAGE24_FORBIDDEN_VOCABULARY_WORDS:
                assert forbidden not in words, (
                    f"{path}: identifier {ident!r} carries forbidden "
                    f"word-level token {forbidden!r}"
                )


def test_new_module_identifiers_avoid_forbidden_routing_tokens():
    for path in _iter_new_modules():
        idents = _extract_all_identifiers(_read_source(path))
        for ident in idents:
            lower = ident.lower()
            for forbidden in STAGE24_FORBIDDEN_ROUTING_TOKENS:
                assert forbidden not in lower, (
                    f"{path}: identifier {ident!r} contains forbidden "
                    f"routing-token substring {forbidden!r}"
                )


# ---------------------------------------------------------------------------
# Stage 24 vocabulary positively allowed
# ---------------------------------------------------------------------------


def test_jito_tip_module_uses_jito_tip_vocabulary():
    """``jito_tip.py`` MUST carry the Stage 24 vocabulary so the
    file is actually doing what its name implies. Negative sanity
    check on the boundary scanner: the Stage 24 vocabulary is NOT
    falsely banned.
    """
    source = _read_source(STAGE24_ROOT / "jito_tip.py")
    idents = _extract_all_identifiers(source)
    lowered = {i.lower() for i in idents}
    assert any("jito" in i for i in lowered)
    assert any("tip" in i for i in lowered)


# ---------------------------------------------------------------------------
# Base64 reuse policy
# ---------------------------------------------------------------------------


def test_jito_tip_module_may_import_base64():
    """``jito_tip.py`` is allowed to import ``base64`` because
    decoding the System Program Transfer instruction-data bytes is
    its job. Mirrors the ``compute_budget.py`` policy.
    """
    source = _read_source(STAGE24_ROOT / "jito_tip.py")
    tree = ast.parse(source)
    saw_base64 = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "base64":
                    saw_base64 = True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "base64":
                saw_base64 = True
    assert saw_base64, (
        "jito_tip.py is expected to import base64 for "
        "System Program transfer instruction-byte decoding"
    )


def test_jito_tip_module_does_not_import_solana_sdk_or_network_libs():
    source = _read_source(STAGE24_ROOT / "jito_tip.py")
    tree = ast.parse(source)
    forbidden_tops: frozenset[str] = frozenset(
        {
            "solana",
            "solders",
            "anchorpy",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
        }
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top not in forbidden_tops, (
                    f"jito_tip.py: forbidden import {alias.name!r}"
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            top = mod.split(".")[0]
            assert top not in forbidden_tops, (
                f"jito_tip.py: forbidden from-import {mod!r}"
            )


def test_jito_tip_module_imports_known_jito_tip_accounts_constant():
    source = _read_source(STAGE24_ROOT / "jito_tip.py")
    tree = ast.parse(source)
    saw_known_jito_tip_accounts = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "PHX2.stage24.constants":
                for alias in node.names:
                    if alias.name == "KNOWN_JITO_TIP_ACCOUNTS":
                        saw_known_jito_tip_accounts = True
    assert saw_known_jito_tip_accounts, (
        "jito_tip.py must import KNOWN_JITO_TIP_ACCOUNTS from "
        "PHX2.stage24.constants"
    )


def test_jito_tip_module_imports_system_program_id_constant():
    source = _read_source(STAGE24_ROOT / "jito_tip.py")
    tree = ast.parse(source)
    saw_system_program_id = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "PHX2.stage24.constants":
                for alias in node.names:
                    if alias.name == "SYSTEM_PROGRAM_ID":
                        saw_system_program_id = True
    assert saw_system_program_id, (
        "jito_tip.py must import SYSTEM_PROGRAM_ID from "
        "PHX2.stage24.constants"
    )


# ---------------------------------------------------------------------------
# Negative fixtures (collector sanity)
# ---------------------------------------------------------------------------


def test_collector_catches_phx2_stage23_import():
    source = "from PHX2.stage23.constants import STAGE23_VERSION\n"
    targets = _collect_full_import_targets(source)
    flagged = False
    for target in targets:
        for forbidden in _FORBIDDEN_PRIOR_STAGE_PRODUCTION_PREFIXES:
            if target.startswith(forbidden):
                flagged = True
    assert flagged


def test_env_detector_catches_plain_os_environ():
    source = "import os\nx = os.environ['KEY']\n"
    assert _module_reads_env_in_source(source)


def test_env_detector_ignores_docstring_mention():
    source = '"""os.environ never read."""\n'
    assert not _module_reads_env_in_source(source)
