"""Stage 22.4 file-scoped boundary tests for the failure-handling module.

The shared Stage 22 boundary tests in
``test_stage_22_1_boundaries.py`` already enforce the rolling
production-tree scope on every Stage 22 production module
including the new ``failure_handling.py``. This file pins the
22.4-specific properties of that module:

  * ``STAGE22_MINOR_VERSION`` is ``"22.5"`` (rolling minor-version axis).
  * The module's import set is exactly the locked allowlist.
  * The module performs no env reads.
  * The module uses no forbidden filesystem mutators
    (``mkdir`` / ``unlink`` / ``rename`` / ``replace`` /
    ``glob`` / ``iterdir`` / ``rmdir``) and no ``shutil``.
  * The module has no top-level I/O call.
  * The module has no clock-related import or attribute use
    (``time``, ``datetime``, ``calendar``, ``asyncio``).
  * The module's source text contains no URL literal, no
    secret-bearing field-name substring, no Stage 23+
    vocabulary, no forbidden routing token.
  * The module does NOT import ``PHX2.stage21`` directly.
  * Exactly one Stage 22.4 test file is permitted to import
    ``PHX2.stage21.provider_event_decoder``: the real-decoder
    integration test. Every other 22.4 test file uses an
    injected fake decoder.
  * ``failure_handling.py`` is on the rolling production-file
    locked set declared in ``test_stage_22_1_boundaries.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage22 import constants as c


STAGE22_ROOT: Path = (
    Path(__file__).parent.parent.parent / "stage22"
)
FAILURE_HANDLING_PATH: Path = STAGE22_ROOT / "failure_handling.py"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _read_source() -> str:
    return FAILURE_HANDLING_PATH.read_text(encoding="utf-8")


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


def _collect_identifiers() -> set[str]:
    idents: set[str] = set()
    for node in ast.walk(_tree()):
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
# Version axis
# ---------------------------------------------------------------------------


def test_stage22_minor_version_is_22_5():
    assert c.STAGE22_MINOR_VERSION == "22.5"


# ---------------------------------------------------------------------------
# Production file presence
# ---------------------------------------------------------------------------


def test_failure_handling_module_exists():
    assert FAILURE_HANDLING_PATH.is_file()


# ---------------------------------------------------------------------------
# Locked import allowlist
# ---------------------------------------------------------------------------


_ALLOWED_IMPORT_PREFIXES: tuple[str, ...] = (
    "__future__",
    "hashlib",
    "json",
    "collections.abc",
    "typing",
    "PHX2.stage22.constants",
    "PHX2.stage22.errors",
    "PHX2.stage22.ingest_contracts",
    "PHX2.stage22.failure_classification",
)


def test_failure_handling_imports_are_within_locked_allowlist():
    imports = _collect_imports()
    for mod in imports:
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
    # Provider clients
    "helius",
    "birdeye",
    "dexscreener",
    "jupiter",
    "jito",
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
    # CLI / sleep / async / file persistence
    "argparse",
    "click",
    "typer",
    "fire",
    "docopt",
    "time",
    "asyncio",
    "pathlib",
    "shutil",
    "tempfile",
    "csv",
    "os",
)


def test_failure_handling_no_forbidden_module_patterns():
    for mod in _collect_imports():
        lower = mod.lower()
        for pattern in _FORBIDDEN_IMPORT_PATTERNS:
            assert pattern not in lower, (
                f"forbidden module pattern {pattern!r} in import {mod!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden Phoenix1 / prior-stage / runtime-layer imports
# ---------------------------------------------------------------------------


_FORBIDDEN_PHX2_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
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


_FORBIDDEN_STAGE21_NEIGHBOURS: tuple[str, ...] = (
    "PHX2.stage21.fake_provider",
    "PHX2.stage21.fake_transport",
    "PHX2.stage21.live_path_simulator",
    "PHX2.stage21.provider_adapter_helius",
    "PHX2.stage21.discord_private_transport",
    "PHX2.stage21.private_smoke_runner",
    "PHX2.stage21.config",
    "PHX2.stage21.live_secrets_boundary",
    "PHX2.stage21.provider_event_decoder",
)


def test_failure_handling_no_phoenix1_imports():
    for target in _collect_full_import_targets():
        assert not target.startswith("phoenix1"), (
            f"forbidden phoenix1 import target: {target!r}"
        )


def test_failure_handling_no_forbidden_phx2_prefix_imports():
    for target in _collect_full_import_targets():
        for forbidden in _FORBIDDEN_PHX2_PREFIXES:
            assert not target.startswith(forbidden), (
                f"forbidden import target {target!r} matches {forbidden!r}"
            )


def test_failure_handling_no_forbidden_stage21_neighbour_imports():
    for mod in _collect_imports():
        for forbidden in _FORBIDDEN_STAGE21_NEIGHBOURS:
            assert mod != forbidden, (
                f"forbidden stage21 neighbour import: {mod!r}"
            )


def test_failure_handling_does_not_import_stage21_directly():
    """Stage 22.4 production must not import PHX2.stage21 at all.

    The Stage 21 ``NormalizedLiveEvent`` type reaches this
    module transitively via ``PHX2.stage22.ingest_contracts``;
    the Stage 21 decoder reaches this seam only via the
    caller-supplied ``decode_event_fn`` callable.
    """
    for mod in _collect_imports():
        assert not mod.startswith("PHX2.stage21"), (
            f"failure_handling.py must not import PHX2.stage21 directly; "
            f"got {mod!r}"
        )


# ---------------------------------------------------------------------------
# Env-read discipline
# ---------------------------------------------------------------------------


def test_failure_handling_no_env_read_attribute_access():
    for attr in _collect_attribute_names():
        assert attr not in {"environ", "getenv", "environb"}, (
            f"forbidden env-read attribute: os.{attr}"
        )


def test_failure_handling_no_environ_import_from():
    for target in _collect_full_import_targets():
        assert target != "os.environ"
        assert target != "os.getenv"
        assert target != "os.environb"


# ---------------------------------------------------------------------------
# Filesystem-mutator discipline
# ---------------------------------------------------------------------------


_FORBIDDEN_PATH_METHODS: tuple[str, ...] = (
    "mkdir",
    "unlink",
    "rename",
    "replace",
    "glob",
    "iterdir",
    "rmdir",
)


def test_failure_handling_no_forbidden_path_mutators():
    for attr in _collect_attribute_names():
        assert attr not in _FORBIDDEN_PATH_METHODS, (
            f"forbidden filesystem-mutator attribute: .{attr}"
        )


# ---------------------------------------------------------------------------
# Clock discipline
# ---------------------------------------------------------------------------


_FORBIDDEN_CLOCK_IMPORTS: tuple[str, ...] = (
    "time",
    "datetime",
    "calendar",
    "asyncio",
)


def test_failure_handling_no_clock_imports():
    for mod in _collect_imports():
        top = mod.split(".")[0]
        assert top not in _FORBIDDEN_CLOCK_IMPORTS, (
            f"forbidden clock-related import: {mod!r}"
        )


# ---------------------------------------------------------------------------
# AST / structural discipline
# ---------------------------------------------------------------------------


def test_failure_handling_no_async_function_def():
    for node in ast.walk(_tree()):
        assert not isinstance(node, ast.AsyncFunctionDef)


def test_failure_handling_no_async_for():
    for node in ast.walk(_tree()):
        assert not isinstance(node, ast.AsyncFor)


def test_failure_handling_no_async_with():
    for node in ast.walk(_tree()):
        assert not isinstance(node, ast.AsyncWith)


def test_failure_handling_no_while_loop():
    for node in ast.walk(_tree()):
        assert not isinstance(node, ast.While)


def test_failure_handling_no_main_guard():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Compare):
            participants = [node.left] + list(node.comparators)
            has_dunder_name = any(
                isinstance(p, ast.Name) and p.id == "__name__"
                for p in participants
            )
            has_dunder_main = any(
                isinstance(p, ast.Constant) and p.value == "__main__"
                for p in participants
            )
            assert not (has_dunder_name and has_dunder_main), (
                "forbidden __name__ == '__main__' guard in "
                "failure_handling.py"
            )


def test_failure_handling_no_top_level_main_or_cli_function():
    forbidden = frozenset({"main", "cli", "entrypoint"})
    for node in _tree().body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in forbidden, (
                f"forbidden top-level entrypoint function: {node.name!r}"
            )


# ---------------------------------------------------------------------------
# Top-level call discipline (no I/O at import)
# ---------------------------------------------------------------------------


class _TopLevelCallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.depth: int = 0
        self.calls: list[ast.Call] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> None:
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
    "fsync",
    "mkdir",
    "unlink",
    "rename",
    "replace",
    "rmdir",
    "glob",
    "iterdir",
    "write",
    "read",
    "load",
    "loads",
    "dump",
    "dumps",
    "Path",
)


def test_failure_handling_no_forbidden_top_level_calls():
    collector = _TopLevelCallCollector()
    collector.visit(_tree())
    names: set[str] = set()
    for call in collector.calls:
        func: ast.expr = call.func
        while isinstance(func, ast.Attribute):
            names.add(func.attr)
            func = func.value
        if isinstance(func, ast.Name):
            names.add(func.id)
    leaked = sorted(names & set(_FORBIDDEN_TOP_LEVEL_CALL_NAMES))
    assert not leaked, (
        f"forbidden top-level calls in failure_handling.py: {leaked}"
    )


def test_failure_handling_top_level_is_side_effect_free():
    allowed_top_level = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.FunctionDef,
        ast.Assign,
        ast.AnnAssign,
        ast.Expr,  # docstrings live inside Expr nodes
    )
    for node in _tree().body:
        assert isinstance(node, allowed_top_level), (
            f"unexpected top-level node {type(node).__name__}"
        )


# ---------------------------------------------------------------------------
# Source-text discipline
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_SUBSTRINGS: tuple[str, ...] = (
    "https" + ":" + "//",
    "http" + ":" + "//",
    "wss" + ":" + "//",
    "ws" + ":" + "//",
    "discord" + "." + "com",
    "discordapp" + "." + "com",
    "hooks" + ".slack" + "." + "com",
)


def test_failure_handling_no_url_literal_in_source():
    source = _read_source()
    for needle in _FORBIDDEN_URL_SUBSTRINGS:
        assert needle not in source, (
            f"forbidden URL literal in source: {needle!r}"
        )


def test_failure_handling_no_bot_db_reference_in_source():
    source = _read_source()
    assert "bot.db" not in source


def test_failure_handling_no_forbidden_routing_token_in_source():
    source = _read_source()
    for token in c.STAGE22_FORBIDDEN_ROUTING_TOKENS:
        assert token not in source, (
            f"forbidden routing token {token!r} in source"
        )


# ---------------------------------------------------------------------------
# Vocabulary discipline
# ---------------------------------------------------------------------------


def test_failure_handling_no_forbidden_vocabulary_in_identifiers():
    for ident in _collect_identifiers():
        lower = ident.lower()
        for forbidden in c.STAGE22_FORBIDDEN_VOCABULARY:
            assert forbidden not in lower, (
                f"identifier {ident!r} contains forbidden vocabulary "
                f"substring {forbidden!r}"
            )


# ---------------------------------------------------------------------------
# Field-name discipline
# ---------------------------------------------------------------------------


_FORBIDDEN_FIELD_NAME_SUBSTRINGS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "webhook_url",
    "webhook",
    "rpc_url",
    "raw_response_body",
    "raw_response",
    "response_body",
    "exception_message",
    "exception_repr",
    "exception_args",
    "headers",
    "authorization",
    "bearer",
    "password",
    "secret",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
)


def test_failure_handling_no_class_body_field_with_secret_name():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(
                    item.target, ast.Name
                ):
                    lower = item.target.id.lower()
                    for forbidden in _FORBIDDEN_FIELD_NAME_SUBSTRINGS:
                        assert forbidden not in lower, (
                            f"class {node.name!r} field "
                            f"{item.target.id!r} contains forbidden "
                            f"secret-bearing substring {forbidden!r}"
                        )


# ---------------------------------------------------------------------------
# Stage 23+ vocabulary forbidden in 22.4
# ---------------------------------------------------------------------------


_STAGE23_FORBIDDEN_VOCABULARY: tuple[str, ...] = (
    "instruction_kind",
    "all_time_high",
    "migration",
    "filter",
    "holder",
    "wallet",
    "monetization",
)


def test_failure_handling_no_stage_23_plus_vocabulary_in_identifiers():
    for ident in _collect_identifiers():
        lower = ident.lower()
        for forbidden in _STAGE23_FORBIDDEN_VOCABULARY:
            assert forbidden not in lower, (
                f"identifier {ident!r} contains forbidden Stage 23+ "
                f"vocabulary substring {forbidden!r}"
            )


# ---------------------------------------------------------------------------
# Stage 22 import-allowlist check at the file level
# ---------------------------------------------------------------------------


_ALLOWED_STAGE22_FROM_TARGETS: tuple[str, ...] = (
    "PHX2.stage22.constants",
    "PHX2.stage22.errors",
    "PHX2.stage22.ingest_contracts",
    "PHX2.stage22.failure_classification",
)


def test_failure_handling_stage22_imports_only_from_locked_surface():
    for mod in _collect_imports():
        if mod.startswith("PHX2.stage22"):
            assert mod in _ALLOWED_STAGE22_FROM_TARGETS, (
                f"failure_handling.py imports unexpected Stage 22 module "
                f"{mod!r}; allowed: {_ALLOWED_STAGE22_FROM_TARGETS}"
            )


# ---------------------------------------------------------------------------
# Locked Stage 22.4 production-file presence in the rolling set
# ---------------------------------------------------------------------------


def test_failure_handling_filename_is_in_rolling_locked_set():
    rolling_boundary_path = (
        Path(__file__).parent / "test_stage_22_1_boundaries.py"
    )
    source = rolling_boundary_path.read_text(encoding="utf-8")
    assert '"failure_handling.py"' in source, (
        "rolling locked-files set in test_stage_22_1_boundaries.py "
        "must include \"failure_handling.py\""
    )


# ---------------------------------------------------------------------------
# Stage22BatchHandlingResult shape
# ---------------------------------------------------------------------------


def test_stage22_batch_handling_result_field_order():
    from PHX2.stage22.failure_handling import Stage22BatchHandlingResult
    assert Stage22BatchHandlingResult._fields == (
        "outcome",
        "provider_id",
        "chain",
        "provider_attempt_index",
        "events_received",
        "events_normalized",
        "events_malformed",
        "provider_failures",
        "last_failure_label",
        "envelopes",
    )


# ---------------------------------------------------------------------------
# Test-file allowlist: ONE test file may import Stage 21 decoder
# ---------------------------------------------------------------------------


_STAGE22_TESTS_DIR: Path = Path(__file__).parent


def _iter_failure_handling_test_files() -> list[Path]:
    return sorted(
        p for p in _STAGE22_TESTS_DIR.glob("test_failure_handling*.py")
        if p.is_file()
    )


def _file_imports_stage21_decoder(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "PHX2.stage21.provider_event_decoder":
                return True
            if mod.startswith("PHX2.stage21.provider_event_decoder."):
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    alias.name == "PHX2.stage21.provider_event_decoder"
                    or alias.name.startswith(
                        "PHX2.stage21.provider_event_decoder."
                    )
                ):
                    return True
    return False


def test_exactly_one_failure_handling_test_file_imports_stage21_decoder():
    """The Stage 22.4 design lock allows ONE dedicated integration
    test file to import the Stage 21.3A real decoder. Every other
    Stage 22.4 test file uses an injected fake decoder.
    """
    importers = [
        p for p in _iter_failure_handling_test_files()
        if _file_imports_stage21_decoder(p)
    ]
    assert len(importers) == 1, (
        f"exactly one failure_handling test file may import the "
        f"Stage 21.3A real decoder; got {len(importers)}: "
        f"{[p.name for p in importers]}"
    )
    assert importers[0].name == (
        "test_failure_handling_real_decoder_integration.py"
    )
