"""Stage 23.5 file-scoped boundary tests for the runner and writer.

The rolling Stage 23 boundary tests in
``test_stage_23_1_boundaries.py`` already enforce the Stage 23
production-tree invariants (locked filenames, forbidden
filenames, vocabulary scan, env-read prohibition, no top-level
I/O calls, etc.) on every Stage 23 production module including
the new ``runner.py`` and ``artifact_writer.py``. This file pins
the 23.5-specific properties of the runner / writer modules:

  * ``runner.py`` and ``artifact_writer.py`` exist.
  * Each module's import set is exactly the locked allowlist.
  * Neither module performs env reads.
  * Neither module imports network / RPC / messaging / DB /
    SQLite / SQLAlchemy / scheduler / secrets-management
    libraries.
  * Neither module imports Stage 21 / Stage 22 production
    modules, PHX2 runtime-layer modules, or Phoenix1 filter
    modules.
  * The runner has no top-level I/O call.
  * The writer has no top-level I/O call.
  * Neither module's source carries a URL literal, webhook host
    literal, ``bot.db`` reference, hardcoded smoke path, or a
    public / subscriber routing string.
  * Neither module's source contains enforcement / blocking
    language (e.g. ``enforce``, ``block_token``).
  * Stage 21 / Stage 22 production trees are present and the
    Stage 23 closure files are present (snapshot checks).
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage23 import artifact_writer as aw
from PHX2.stage23 import runner as rn


STAGE23_ROOT: Path = (
    Path(__file__).parent.parent.parent / "stage23"
)
RUNNER_PATH: Path = STAGE23_ROOT / "runner.py"
ARTIFACT_WRITER_PATH: Path = STAGE23_ROOT / "artifact_writer.py"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_read_source(path))


def _collect_imports(path: Path) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def _collect_full_import_targets(path: Path) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(_tree(path)):
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


def _collect_attribute_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


# ---------------------------------------------------------------------------
# Production file presence
# ---------------------------------------------------------------------------


def test_runner_module_exists():
    assert RUNNER_PATH.is_file()


def test_artifact_writer_module_exists():
    assert ARTIFACT_WRITER_PATH.is_file()


# ---------------------------------------------------------------------------
# Locked import allowlists
# ---------------------------------------------------------------------------


_RUNNER_ALLOWED_IMPORT_PREFIXES: tuple[str, ...] = (
    "__future__",
    "collections",
    "types",
    "typing",
    "PHX2.stage23.constants",
    "PHX2.stage23.errors",
    "PHX2.stage23.filter_contracts",
    "PHX2.stage23.holder_concentration",
    "PHX2.stage23.launch_structure",
    "PHX2.stage23.models",
    "PHX2.stage23.wallet_source_quality",
)


_ARTIFACT_WRITER_ALLOWED_IMPORT_PREFIXES: tuple[str, ...] = (
    "__future__",
    "collections",
    "hashlib",
    "pathlib",
    "types",
    "typing",
    "PHX2.stage23.constants",
    "PHX2.stage23.errors",
    # Stage 23.6: the writer imports the input reader's
    # ``stage23_value_carries_leak_shape`` helper so the
    # pre-write redaction sweep can detect long hex / tokenish /
    # env-name leak shapes on user-controllable values that
    # bypassed the input reader at ingest.
    "PHX2.stage23.input_reader",
    "PHX2.stage23.models",
    "PHX2.stage23.runner",
    "PHX2.stage23.stage23_manifest",
)


def test_runner_imports_are_within_locked_allowlist():
    for mod in _collect_imports(RUNNER_PATH):
        assert any(
            mod == prefix or mod.startswith(prefix + ".")
            for prefix in _RUNNER_ALLOWED_IMPORT_PREFIXES
        ), f"unexpected runner import target: {mod!r}"


def test_artifact_writer_imports_are_within_locked_allowlist():
    for mod in _collect_imports(ARTIFACT_WRITER_PATH):
        assert any(
            mod == prefix or mod.startswith(prefix + ".")
            for prefix in _ARTIFACT_WRITER_ALLOWED_IMPORT_PREFIXES
        ), f"unexpected artifact_writer import target: {mod!r}"


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
    "psycopg",
    "asyncpg",
    "mysql",
    # Secrets
    "dotenv",
    "keyring",
    # CLI / sleep
    "argparse",
    "click",
    "typer",
    "fire",
    "docopt",
    "asyncio",
    # Wallet-graph crawler / provenance ground-truth clients
    "neo4j",
    "networkx",
    "py2neo",
    "etherscan",
    "solscan",
)


def test_runner_no_forbidden_module_patterns():
    for mod in _collect_imports(RUNNER_PATH):
        lower = mod.lower()
        for pattern in _FORBIDDEN_IMPORT_PATTERNS:
            assert pattern not in lower, (
                f"runner: forbidden module pattern {pattern!r} in "
                f"import {mod!r}"
            )


def test_artifact_writer_no_forbidden_module_patterns():
    for mod in _collect_imports(ARTIFACT_WRITER_PATH):
        lower = mod.lower()
        for pattern in _FORBIDDEN_IMPORT_PATTERNS:
            assert pattern not in lower, (
                f"artifact_writer: forbidden module pattern "
                f"{pattern!r} in import {mod!r}"
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


def _assert_no_phoenix1_imports(path: Path) -> None:
    for target in _collect_full_import_targets(path):
        assert not target.startswith("phoenix1"), (
            f"{path.name}: forbidden phoenix1 import target {target!r}"
        )


def _assert_no_forbidden_phx2_prefix_imports(path: Path) -> None:
    for target in _collect_full_import_targets(path):
        for forbidden in _FORBIDDEN_PHX2_PREFIXES:
            assert not target.startswith(forbidden), (
                f"{path.name}: forbidden import target {target!r} "
                f"matches {forbidden!r}"
            )


def test_runner_no_phoenix1_imports():
    _assert_no_phoenix1_imports(RUNNER_PATH)


def test_artifact_writer_no_phoenix1_imports():
    _assert_no_phoenix1_imports(ARTIFACT_WRITER_PATH)


def test_runner_no_forbidden_phx2_prefix_imports():
    _assert_no_forbidden_phx2_prefix_imports(RUNNER_PATH)


def test_artifact_writer_no_forbidden_phx2_prefix_imports():
    _assert_no_forbidden_phx2_prefix_imports(ARTIFACT_WRITER_PATH)


# ---------------------------------------------------------------------------
# Env-read discipline
# ---------------------------------------------------------------------------


def _assert_no_os_import(path: Path) -> None:
    for mod in _collect_imports(path):
        assert mod != "os" and not mod.startswith("os."), (
            f"{path.name}: forbidden os import: {mod!r}"
        )


def _assert_no_env_attr(path: Path) -> None:
    attrs = _collect_attribute_names(path)
    forbidden = {"environ", "environb", "getenv"}
    leaked = attrs & forbidden
    assert not leaked, (
        f"{path.name}: forbidden environment-read attribute(s): "
        f"{sorted(leaked)}"
    )


def test_runner_does_not_import_os():
    _assert_no_os_import(RUNNER_PATH)


def test_artifact_writer_does_not_import_os():
    _assert_no_os_import(ARTIFACT_WRITER_PATH)


def test_runner_does_not_reference_environ_or_getenv():
    _assert_no_env_attr(RUNNER_PATH)


def test_artifact_writer_does_not_reference_environ_or_getenv():
    _assert_no_env_attr(ARTIFACT_WRITER_PATH)


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


def _assert_no_url_literal(path: Path) -> None:
    source = _read_source(path)
    for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
        assert needle not in source, (
            f"{path.name}: forbidden URL literal {needle!r} in source"
        )


def test_runner_no_url_literal_in_source():
    _assert_no_url_literal(RUNNER_PATH)


def test_artifact_writer_no_url_literal_in_source():
    _assert_no_url_literal(ARTIFACT_WRITER_PATH)


def _assert_no_bot_db_reference(path: Path) -> None:
    source = _read_source(path)
    assert "bot.db" not in source


def test_runner_no_bot_db_reference_in_source():
    _assert_no_bot_db_reference(RUNNER_PATH)


def test_artifact_writer_no_bot_db_reference_in_source():
    _assert_no_bot_db_reference(ARTIFACT_WRITER_PATH)


# Hardcoded smoke-path / live-path literals.
_FORBIDDEN_HARDCODED_SMOKE_PATH_SUBSTRINGS: tuple[str, ...] = (
    "C:\\Users",
    "C:/Users",
    "/Users/",
    "/home/",
    "/var/lib",
    "Phoenix_PHX2",
    "PHX2/.stage_17",
    "PHX2\\.stage_17",
)


def _assert_no_hardcoded_smoke_path(path: Path) -> None:
    source = _read_source(path)
    for needle in _FORBIDDEN_HARDCODED_SMOKE_PATH_SUBSTRINGS:
        assert needle not in source, (
            f"{path.name}: forbidden hardcoded smoke-path substring "
            f"{needle!r} in source"
        )


def test_runner_no_hardcoded_smoke_path_literal():
    _assert_no_hardcoded_smoke_path(RUNNER_PATH)


def test_artifact_writer_no_hardcoded_smoke_path_literal():
    _assert_no_hardcoded_smoke_path(ARTIFACT_WRITER_PATH)


# Public / subscriber routing strings.
_FORBIDDEN_PUBLIC_SUBSCRIBER_ROUTING_TOKENS: tuple[str, ...] = (
    "subscriber",
    "subscribers",
    "public_channel",
    "public_signal",
    "public_dispatch",
    "paid_signal",
    "paid_channel",
)


def _assert_no_public_subscriber_routing(path: Path) -> None:
    source = _read_source(path)
    lower = source.lower()
    for needle in _FORBIDDEN_PUBLIC_SUBSCRIBER_ROUTING_TOKENS:
        assert needle not in lower, (
            f"{path.name}: forbidden public/subscriber routing "
            f"substring {needle!r} in source"
        )


def test_runner_no_public_subscriber_routing_strings():
    _assert_no_public_subscriber_routing(RUNNER_PATH)


def test_artifact_writer_no_public_subscriber_routing_strings():
    _assert_no_public_subscriber_routing(ARTIFACT_WRITER_PATH)


# Enforcement / blocking language in identifiers.
#
# Stage 23 is observe-only; the runner/writer must not introduce
# any enforcement/gating/blocking vocabulary at the identifier
# level. Substrings scanned here:
#
#   * ``enforce`` -- any enforce / enforced / enforcement family.
#   * ``block_token`` -- the legacy blocking-decision identifier
#     pattern from prior PHX2 stages.
#   * ``block`` and ``blocking`` -- bare blocking-decision
#     vocabulary. Catching the bare substrings prevents drift
#     toward an identifier like ``block_event`` /
#     ``blocking_filter`` that would slip past the more specific
#     ``block_token`` needle.
#   * ``gate_token`` and ``gate`` -- gating-decision vocabulary.
#
# Scanning happens at AST identifier positions ONLY -- function /
# async-function / class definition names and ``ast.Name`` nodes.
# String literals and docstrings are NOT scanned, so legitimate
# negative phrases like "Stage 23 never blocks" in docstrings do
# not produce false positives.
_FORBIDDEN_ENFORCEMENT_TOKENS: tuple[str, ...] = (
    "enforce",
    "block_token",
    "block",
    "blocking",
    "gate_token",
    "gate",
)


def _assert_no_enforcement_identifiers(path: Path) -> None:
    """Scan AST identifier positions for enforcement-language substrings.

    The scan only inspects function / async-function / class
    definition names and ``ast.Name`` references; string literals
    and docstrings are intentionally excluded so negative-form
    phrases ("Stage 23 never blocks...") in docstrings stay
    clean.
    """
    tree = _tree(path)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lower = node.name.lower()
            for needle in _FORBIDDEN_ENFORCEMENT_TOKENS:
                assert needle not in lower, (
                    f"{path.name}: forbidden enforcement identifier "
                    f"{node.name!r} contains {needle!r}"
                )
        elif isinstance(node, ast.Name):
            lower = node.id.lower()
            for needle in _FORBIDDEN_ENFORCEMENT_TOKENS:
                assert needle not in lower, (
                    f"{path.name}: forbidden enforcement identifier "
                    f"{node.id!r} contains {needle!r}"
                )


def test_runner_no_enforcement_identifiers():
    _assert_no_enforcement_identifiers(RUNNER_PATH)


def test_artifact_writer_no_enforcement_identifiers():
    _assert_no_enforcement_identifiers(ARTIFACT_WRITER_PATH)


# ---------------------------------------------------------------------------
# Locked filter / writer identity surface
# ---------------------------------------------------------------------------


def test_runner_reason_code_set_is_locked():
    assert rn.STAGE23_RUNNER_REASON_CODES == (
        "STAGE23_FILTER_RAISED_ERROR",
    )


def test_artifact_writer_manifest_kind_is_locked():
    assert (
        aw.STAGE23_RUNNER_ARTIFACT_MANIFEST_KIND
        == "stage23_runner_artifact"
    )


# ---------------------------------------------------------------------------
# Stage 21 / Stage 22 production trees untouched
# ---------------------------------------------------------------------------


REPO_ROOT: Path = Path(__file__).parent.parent.parent
STAGE21_ROOT: Path = REPO_ROOT / "stage21"
STAGE22_ROOT: Path = REPO_ROOT / "stage22"


def test_stage21_production_tree_is_present():
    assert STAGE21_ROOT.is_dir()


def test_stage22_production_tree_is_present():
    assert STAGE22_ROOT.is_dir()


def test_stage22_dedupe_ledger_module_still_present():
    assert (STAGE22_ROOT / "dedupe_ledger.py").is_file()


def test_stage22_raw_capture_module_still_present():
    assert (STAGE22_ROOT / "raw_capture.py").is_file()


def test_stage22_bounded_live_runner_module_still_present():
    assert (STAGE22_ROOT / "bounded_live_runner.py").is_file()


def test_stage23_holder_concentration_module_still_present():
    assert (STAGE23_ROOT / "holder_concentration.py").is_file()


def test_stage23_launch_structure_module_still_present():
    assert (STAGE23_ROOT / "launch_structure.py").is_file()


def test_stage23_wallet_source_quality_module_still_present():
    assert (STAGE23_ROOT / "wallet_source_quality.py").is_file()


# ---------------------------------------------------------------------------
# CLI / __main__ guard absence
# ---------------------------------------------------------------------------


def _assert_no_dunder_main_guard(path: Path) -> None:
    for node in ast.walk(_tree(path)):
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
                f"{path.name}: must not carry a __name__ guard"
            )


def _assert_no_top_level_main_or_cli_function(path: Path) -> None:
    forbidden_entrypoint_names = {"main", "cli", "entrypoint"}
    for node in _tree(path).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in forbidden_entrypoint_names, (
                f"{path.name}: forbidden CLI-style entrypoint "
                f"function {node.name!r}"
            )


def test_runner_no_dunder_main_guard():
    _assert_no_dunder_main_guard(RUNNER_PATH)


def test_artifact_writer_no_dunder_main_guard():
    _assert_no_dunder_main_guard(ARTIFACT_WRITER_PATH)


def test_runner_no_top_level_main_or_cli_function():
    _assert_no_top_level_main_or_cli_function(RUNNER_PATH)


def test_artifact_writer_no_top_level_main_or_cli_function():
    _assert_no_top_level_main_or_cli_function(ARTIFACT_WRITER_PATH)


# ---------------------------------------------------------------------------
# Forbidden runtime callables at top level
# ---------------------------------------------------------------------------


# Stage 23.5 introduces an artifact writer that calls ``open()``
# inside a write-helper function. The Stage 23.1 rolling boundary
# test forbids top-level ``open`` calls; the writer's call is
# nested inside a function so this stricter file-scoped test
# explicitly excludes ``open`` from the forbidden top-level set
# for the writer module while still pinning every other
# I/O / network / sleep callable.
_FORBIDDEN_TOP_LEVEL_CALL_NAMES: tuple[str, ...] = (
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


def test_no_forbidden_top_level_calls_in_runner():
    names = _collect_top_level_call_names(_read_source(RUNNER_PATH))
    leaked = sorted(set(names) & set(_FORBIDDEN_TOP_LEVEL_CALL_NAMES))
    assert not leaked, (
        f"forbidden top-level call(s) in runner: {leaked}"
    )


def test_no_forbidden_top_level_calls_in_artifact_writer():
    names = _collect_top_level_call_names(
        _read_source(ARTIFACT_WRITER_PATH)
    )
    leaked = sorted(set(names) & set(_FORBIDDEN_TOP_LEVEL_CALL_NAMES))
    assert not leaked, (
        f"forbidden top-level call(s) in artifact_writer: {leaked}"
    )


# ---------------------------------------------------------------------------
# Writer does not call Path.write_text / Path.write_bytes
# ---------------------------------------------------------------------------


def test_artifact_writer_does_not_call_write_text_or_write_bytes():
    """The writer must use the ``open()`` + ``.write()`` pattern, not
    ``Path.write_text`` / ``Path.write_bytes``. The Stage 23.1
    rolling boundary test forbids those attribute references in
    every Stage 23 production module; this Stage 23.5 file pins
    the writer-specific invariant explicitly.
    """
    attrs = _collect_attribute_names(ARTIFACT_WRITER_PATH)
    forbidden = {"write_text", "write_bytes"}
    leaked = attrs & forbidden
    assert not leaked, (
        f"artifact_writer: forbidden disk-write attribute(s) "
        f"{sorted(leaked)}"
    )


def test_runner_does_not_call_write_text_or_write_bytes():
    attrs = _collect_attribute_names(RUNNER_PATH)
    forbidden = {"write_text", "write_bytes"}
    leaked = attrs & forbidden
    assert not leaked, (
        f"runner: forbidden disk-write attribute(s) {sorted(leaked)}"
    )


# ---------------------------------------------------------------------------
# No alert dispatch / Discord / Telegram surface
# ---------------------------------------------------------------------------


_FORBIDDEN_DISPATCH_TOKENS: tuple[str, ...] = (
    "dispatch_alert",
    "send_alert",
    "alert_dispatch",
    "send_to_discord",
    "send_to_telegram",
    "publish_alert",
)


def _assert_no_dispatch_identifiers(path: Path) -> None:
    source = _read_source(path)
    lower = source.lower()
    for needle in _FORBIDDEN_DISPATCH_TOKENS:
        assert needle not in lower, (
            f"{path.name}: forbidden alert-dispatch substring "
            f"{needle!r} in source"
        )


def test_runner_no_alert_dispatch_identifiers():
    _assert_no_dispatch_identifiers(RUNNER_PATH)


def test_artifact_writer_no_alert_dispatch_identifiers():
    _assert_no_dispatch_identifiers(ARTIFACT_WRITER_PATH)
