"""Stage 22.3 file-scoped boundary tests for the raw capture module.

The shared Stage 22 boundary tests in
``test_stage_22_1_boundaries.py`` already enforce the rolling
production-tree scope on every Stage 22 production module
including the new ``raw_capture.py``. This file pins the
22.3-specific properties of that module:

  * ``STAGE22_MINOR_VERSION`` is ``"22.3"``.
  * The raw capture record-type closed set and schema version
    constants are present and well-formed.
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
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage22 import constants as c


STAGE22_ROOT: Path = (
    Path(__file__).parent.parent.parent / "stage22"
)
RAW_CAPTURE_PATH: Path = STAGE22_ROOT / "raw_capture.py"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _read_source() -> str:
    return RAW_CAPTURE_PATH.read_text(encoding="utf-8")


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
# Version axis + locked constants
# ---------------------------------------------------------------------------


def test_stage22_minor_version_is_22_4():
    assert c.STAGE22_MINOR_VERSION == "22.4"


def test_capture_record_type_normalized_event_is_locked_value():
    assert c.CAPTURE_RECORD_TYPE_NORMALIZED_EVENT == "normalized_event"


def test_capture_record_type_malformed_event_is_locked_value():
    assert c.CAPTURE_RECORD_TYPE_MALFORMED_EVENT == "malformed_event"


def test_capture_record_type_provider_failure_is_locked_value():
    assert c.CAPTURE_RECORD_TYPE_PROVIDER_FAILURE == "provider_failure"


def test_capture_record_types_tuple_is_locked():
    assert c.CAPTURE_RECORD_TYPES == (
        "normalized_event",
        "malformed_event",
        "provider_failure",
    )


def test_stage22_capture_record_schema_version_is_locked():
    assert c.STAGE22_CAPTURE_RECORD_SCHEMA_VERSION == "stage22_v0_capture"


# ---------------------------------------------------------------------------
# Production file presence
# ---------------------------------------------------------------------------


def test_raw_capture_module_exists():
    assert RAW_CAPTURE_PATH.is_file()


# ---------------------------------------------------------------------------
# Locked import allowlist
# ---------------------------------------------------------------------------


_ALLOWED_IMPORT_PREFIXES: tuple[str, ...] = (
    "__future__",
    "json",
    "math",
    "os",
    "pathlib",
    "collections.abc",
    "PHX2.stage22.constants",
    "PHX2.stage22.errors",
    "PHX2.stage22.ingest_contracts",
)


def test_raw_capture_imports_are_within_locked_allowlist():
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
    # CLI / sleep
    "argparse",
    "click",
    "typer",
    "fire",
    "docopt",
    "time",
    "asyncio",
    # File-persistence beyond the allowlist
    "shutil",
    "tempfile",
    "csv",
)


def test_raw_capture_no_forbidden_module_patterns():
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
)


def test_raw_capture_no_phoenix1_imports():
    for target in _collect_full_import_targets():
        assert not target.startswith("phoenix1"), (
            f"forbidden phoenix1 import target: {target!r}"
        )


def test_raw_capture_no_forbidden_phx2_prefix_imports():
    for target in _collect_full_import_targets():
        for forbidden in _FORBIDDEN_PHX2_PREFIXES:
            assert not target.startswith(forbidden), (
                f"forbidden import target {target!r} matches {forbidden!r}"
            )


def test_raw_capture_no_forbidden_stage21_neighbour_imports():
    for mod in _collect_imports():
        for forbidden in _FORBIDDEN_STAGE21_NEIGHBOURS:
            assert mod != forbidden, (
                f"forbidden stage21 neighbour import: {mod!r}"
            )


def test_raw_capture_does_not_import_stage21_directly():
    """Stage 22.3 production must not import PHX2.stage21 at all.

    Stage 21 types reach this module transitively via the
    Stage 22.1 contract surface (IngestEventEnvelope.event is
    typed Stage21 NormalizedLiveEvent, but the import lives in
    ingest_contracts.py, not here).
    """
    for mod in _collect_imports():
        assert not mod.startswith("PHX2.stage21"), (
            f"raw_capture.py must not import PHX2.stage21 directly; "
            f"got {mod!r}"
        )


# ---------------------------------------------------------------------------
# Env-read discipline
# ---------------------------------------------------------------------------


def test_raw_capture_no_env_read_attribute_access():
    """The module uses ``os`` only for ``os.fsync``; it must not
    read ``os.environ`` / ``os.getenv`` / ``os.environb``.
    """
    for attr in _collect_attribute_names():
        assert attr not in {"environ", "getenv", "environb"}, (
            f"forbidden env-read attribute: os.{attr}"
        )


def test_raw_capture_no_environ_import_from():
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


def test_raw_capture_no_forbidden_path_mutators():
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


def test_raw_capture_no_clock_imports():
    for mod in _collect_imports():
        top = mod.split(".")[0]
        assert top not in _FORBIDDEN_CLOCK_IMPORTS, (
            f"forbidden clock-related import: {mod!r}"
        )


# ---------------------------------------------------------------------------
# AST / structural discipline
# ---------------------------------------------------------------------------


def test_raw_capture_no_async_function_def():
    for node in ast.walk(_tree()):
        assert not isinstance(node, ast.AsyncFunctionDef)


def test_raw_capture_no_async_for():
    for node in ast.walk(_tree()):
        assert not isinstance(node, ast.AsyncFor)


def test_raw_capture_no_async_with():
    for node in ast.walk(_tree()):
        assert not isinstance(node, ast.AsyncWith)


def test_raw_capture_no_while_loop():
    for node in ast.walk(_tree()):
        assert not isinstance(node, ast.While)


def test_raw_capture_no_main_guard():
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
                "forbidden __name__ == '__main__' guard in raw_capture.py"
            )


def test_raw_capture_no_top_level_main_or_cli_function():
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


def test_raw_capture_no_forbidden_top_level_calls():
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
    assert not leaked, f"forbidden top-level calls in raw_capture.py: {leaked}"


def test_raw_capture_top_level_is_side_effect_free():
    """Only declarations, imports, and class / function defs are
    allowed at the top level. ``Assign`` / ``AnnAssign`` is
    allowed for module constants like
    ``_REQUIRED_FIELDS_BY_RECORD_TYPE`` and ``__all__``.
    """
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


def test_raw_capture_no_url_literal_in_source():
    source = _read_source()
    for needle in _FORBIDDEN_URL_SUBSTRINGS:
        assert needle not in source, (
            f"forbidden URL literal in source"
        )


def test_raw_capture_no_bot_db_reference_in_source():
    source = _read_source()
    assert "bot.db" not in source


def test_raw_capture_no_forbidden_routing_token_in_source():
    source = _read_source()
    for token in c.STAGE22_FORBIDDEN_ROUTING_TOKENS:
        assert token not in source, (
            f"forbidden routing token {token!r} in source"
        )


# ---------------------------------------------------------------------------
# Vocabulary discipline
# ---------------------------------------------------------------------------


def test_raw_capture_no_forbidden_vocabulary_in_identifiers():
    for ident in _collect_identifiers():
        lower = ident.lower()
        for forbidden in c.STAGE22_FORBIDDEN_VOCABULARY:
            assert forbidden not in lower, (
                f"identifier {ident!r} contains forbidden vocabulary "
                f"substring {forbidden!r}"
            )


# ---------------------------------------------------------------------------
# Field-name discipline on class-body fields
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


def test_raw_capture_no_class_body_field_with_secret_name():
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
# Stage 23+ vocabulary forbidden in 22.3
# ---------------------------------------------------------------------------


_STAGE23_FORBIDDEN_VOCABULARY: tuple[str, ...] = (
    # ``ath`` is intentionally NOT in this tuple -- it is a
    # 3-letter substring that false-positives on legitimate
    # identifiers (``_path`` / ``path``). The Stage 25 ATH
    # boundary will use longer / exact-match tokens.
    "instruction_kind",
    "all_time_high",
    "migration",
    "filter",
    "holder",
    "wallet",
    "monetization",
)


def test_raw_capture_no_stage_23_plus_vocabulary_in_identifiers():
    for ident in _collect_identifiers():
        lower = ident.lower()
        for forbidden in _STAGE23_FORBIDDEN_VOCABULARY:
            assert forbidden not in lower, (
                f"identifier {ident!r} contains forbidden Stage 23+ "
                f"vocabulary substring {forbidden!r}"
            )


# ---------------------------------------------------------------------------
# Stage 22 import-allowlist check at the file level: only ingest_contracts /
# constants / errors from the Stage 22 surface.
# ---------------------------------------------------------------------------


_ALLOWED_STAGE22_FROM_TARGETS: tuple[str, ...] = (
    "PHX2.stage22.constants",
    "PHX2.stage22.errors",
    "PHX2.stage22.ingest_contracts",
)


def test_raw_capture_stage22_imports_only_from_locked_surface():
    for mod in _collect_imports():
        if mod.startswith("PHX2.stage22"):
            assert mod in _ALLOWED_STAGE22_FROM_TARGETS, (
                f"raw_capture.py imports unexpected Stage 22 module "
                f"{mod!r}; allowed: {_ALLOWED_STAGE22_FROM_TARGETS}"
            )


# ---------------------------------------------------------------------------
# Locked Stage 22.3 production-file presence in the rolling set
# ---------------------------------------------------------------------------


def test_raw_capture_filename_is_in_rolling_locked_set():
    """The rolling Stage 22 locked-files set in
    ``test_stage_22_1_boundaries.py`` must include
    ``raw_capture.py``. We grep the source rather than import
    from the test module so this test does not depend on
    PHX2.tests being importable.
    """
    rolling_boundary_path = (
        Path(__file__).parent / "test_stage_22_1_boundaries.py"
    )
    source = rolling_boundary_path.read_text(encoding="utf-8")
    assert '"raw_capture.py"' in source, (
        "rolling locked-files set in test_stage_22_1_boundaries.py "
        "must include \"raw_capture.py\""
    )
