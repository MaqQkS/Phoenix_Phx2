"""Stage 21.3B boundary / scope tests.

Pins the Stage 21.3B scope at the file / import / vocabulary
level. Complementary to the global Stage 21 boundary tests in
``test_import_boundaries.py`` / ``test_env_read_boundaries.py`` /
``test_no_public_routing.py`` / ``test_no_secret_leaks.py``, which
scan every Stage 21 production module. This file pins the 21.3B
specifics:

  * The forbidden 21.3B file set (Discord transport, runner,
    orchestrator, retry/backoff/dedupe/archive, ...) is absent.
  * The new ``provider_adapter_helius.py`` module does NOT
    import any network / messaging / RPC / DB / scheduler /
    secrets-management library.
  * The adapter module does NOT import any prior Stage 17..20
    runtime, Phoenix1, PHX2 runtime layer, or any Stage 21.2
    fake-only module (``fake_provider`` / ``fake_transport`` /
    ``live_path_simulator``).
  * The adapter module does NOT read ``os.environ`` /
    ``os.getenv``.
  * The adapter module top-level is side-effect-free: no
    network / file / socket call appears at import time.
  * The adapter module's identifier vocabulary does NOT
    introduce any retry / backoff / dedupe / archive / send /
    runner / orchestrator / Discord symbol -- those concerns
    belong to Stage 21.3C / 21.4 / 22.
  * The adapter's locked constants
    (``HELIUS_PROVIDER_NAME`` / ``HELIUS_CHAIN_NAME`` /
    ``HELIUS_SOURCE_KIND`` /
    ``HELIUS_INSTRUCTION_KIND_PLACEHOLDER``) match the locked
    values.
  * The decoder's ``SUPPORTED_INSTRUCTION_KINDS`` set is NOT
    widened by Stage 21.3B -- the real instruction-kind
    vocabulary stays deferred.
  * The live-readiness gate's ``PLACEHOLDER_PROVIDER_ID_21_3B``
    is still the locked value -- Stage 21.3B does NOT lift the
    placeholder.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage21.live_secrets_boundary import (
    PLACEHOLDER_PROVIDER_ID_21_3B,
)
from PHX2.stage21.provider_adapter_helius import (
    HELIUS_ADAPTER_LOCKED_VALUES,
    HELIUS_CHAIN_NAME,
    HELIUS_INSTRUCTION_KIND_PLACEHOLDER,
    HELIUS_PROVIDER_NAME,
    HELIUS_SOURCE_KIND,
    HeliusAdapterError,
    REQUIRED_CLIENT_RESPONSE_KEYS,
)
from PHX2.stage21.provider_event_decoder import (
    SUPPORTED_INSTRUCTION_KINDS,
)


STAGE21_ROOT: Path = Path(__file__).parent.parent.parent / "stage21"
PROVIDER_ADAPTER_HELIUS_PATH: Path = (
    STAGE21_ROOT / "provider_adapter_helius.py"
)


# Forbidden Stage 21.3B production filenames. These cover the
# stages explicitly out of scope for 21.3B per the operator
# prompt: runner / orchestrator / live_run (21.4), retry /
# backoff / dedupe / archive (Stage 22), plus the Stage 21.3
# manifest writer (deferred).
#
# NOTE: ``discord_private_transport.py`` was on this list during
# Stage 21.3B but has now landed as the Stage 21.3C boundary. The
# Stage 21.3C boundary test
# (``test_stage_21_3c_boundaries.py``) owns the new file's
# invariants; this 21.3B list is narrowed accordingly so the
# Stage 21.3C landing does not re-fail Stage 21.3B's scope check.
_FORBIDDEN_21_3B_FILE_NAMES: tuple[str, ...] = (
    "stage21_3_manifest.py",
    "runner.py",
    "orchestrator.py",
    "live_run.py",
    "retry.py",
    "backoff.py",
    "dedupe.py",
    "archive.py",
)


# Forbidden runtime libraries the adapter must not import.
# Mirrors the 21.3A boundary set; ``helius`` is excluded here on
# purpose -- the adapter is the *placeholder* for a real Helius
# client but does NOT import any helius-named package directly
# (the future client is injected through the Protocol).
_FORBIDDEN_RUNTIME_LIB_PATTERNS: tuple[str, ...] = (
    # Network / RPC
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    # Provider client packages
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
    # Secrets-management libs
    "dotenv",
    "keyring",
)


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
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


# Adapter must not import the Stage 21.2 fake-only producer or
# the simulator. The adapter is the boundary between Stage 21.2
# fake telemetry and Stage 21.4 live telemetry; mixing the two
# producers would defeat the boundary.
_FORBIDDEN_STAGE21_FAKE_ONLY_MODULES: tuple[str, ...] = (
    "PHX2.stage21.fake_provider",
    "PHX2.stage21.fake_transport",
    "PHX2.stage21.live_path_simulator",
)


# Identifier-position substrings the adapter source MUST NOT
# define. Catches a future drift that introduces a retry helper /
# Discord sender / runner class / dedupe state. Substring match
# is intentional: ``RetryPolicy`` and ``_retry`` both trip.
_FORBIDDEN_ADAPTER_IDENTIFIER_SUBSTRINGS: tuple[str, ...] = (
    "retry",
    "backoff",
    "dedupe",
    "archive",
    "discord",
    "webhook",
    "telegram",
    "orchestrator",
    "scheduler",
    "ratelimit",
    "rate_limit",
)


# Identifier-position substrings the adapter source MUST NOT
# define as a top-level binding or class / function. Narrower
# than the substring scan above; covers tokens that legitimately
# appear in other contexts (e.g. the adapter's docstring
# mentions ``runner`` to describe a future caller).
_FORBIDDEN_ADAPTER_NAMED_DEFINITIONS: tuple[str, ...] = (
    "send",
    "dispatch",
    "publish",
    "transmit",
)


_ENV_ATTR_NAMES: frozenset[str] = frozenset({"environ", "getenv", "environb"})


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_imported_module_paths(path: Path) -> set[str]:
    """Return the set of imported module paths in ``path``."""
    tree = ast.parse(_read_source(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def _module_reads_env(path: Path) -> bool:
    """Return True iff ``path`` reads ``os.environ`` / ``os.getenv``."""
    tree = ast.parse(_read_source(path))
    os_aliases: set[str] = set()
    env_attr_aliases: set[str] = set()
    env_call_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "") == "os":
                for alias in node.names:
                    bound = alias.asname or alias.name
                    if alias.name in ("environ", "environb"):
                        env_attr_aliases.add(bound)
                    elif alias.name == "getenv":
                        env_call_aliases.add(bound)
            elif (node.module or "").startswith("os.environ"):
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


def _extract_defined_identifiers(source: str) -> set[str]:
    """Return identifiers DEFINED at any position in ``source``.

    Covers function / class / argument / target names. Does NOT
    include ``Name`` Load contexts (so an imported name from
    another module does not count as ``defined here``).
    """
    tree = ast.parse(source)
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if isinstance(node.target, ast.Name):
                defined.add(node.target.id)
    return defined


def _extract_all_identifiers(source: str) -> set[str]:
    """Return every identifier appearing at any position in ``source``."""
    tree = ast.parse(source)
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
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
# Stage 21.3B file scope
# ---------------------------------------------------------------------------


def test_provider_adapter_helius_module_exists():
    assert PROVIDER_ADAPTER_HELIUS_PATH.exists(), (
        "Stage 21.3B requires PHX2/stage21/provider_adapter_helius.py"
    )


def test_forbidden_21_3b_production_files_do_not_exist():
    for filename in _FORBIDDEN_21_3B_FILE_NAMES:
        path = STAGE21_ROOT / filename
        assert not path.exists(), (
            f"Stage 21.3B scope violation: {filename} must not exist"
        )


# ---------------------------------------------------------------------------
# Adapter import scope
# ---------------------------------------------------------------------------


def test_adapter_does_not_import_forbidden_runtime_libs():
    modules = _collect_imported_module_paths(PROVIDER_ADAPTER_HELIUS_PATH)
    for module in modules:
        lower = module.lower()
        for pattern in _FORBIDDEN_RUNTIME_LIB_PATTERNS:
            assert pattern not in lower, (
                "provider_adapter_helius.py imports forbidden runtime "
                f"module pattern {pattern!r} via {module!r}"
            )


def test_adapter_does_not_import_prior_stage_or_phoenix1():
    modules = _collect_imported_module_paths(PROVIDER_ADAPTER_HELIUS_PATH)
    for module in modules:
        assert not module.startswith("phoenix1"), (
            f"adapter forbidden phoenix1 import {module!r}"
        )
        for prefix in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
            assert not module.startswith(prefix), (
                f"adapter forbidden prior-stage import {module!r}"
            )


def test_adapter_does_not_import_phx2_runtime_layer():
    modules = _collect_imported_module_paths(PROVIDER_ADAPTER_HELIUS_PATH)
    for module in modules:
        for prefix in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
            assert not module.startswith(prefix), (
                f"adapter forbidden PHX2 runtime-layer import {module!r}"
            )


def test_adapter_does_not_import_stage21_fake_only_modules():
    # The adapter must not cross the fake / live boundary. It
    # must produce live-shaped payloads / events without
    # touching the Stage 21.2 fake producer or the simulator.
    modules = _collect_imported_module_paths(PROVIDER_ADAPTER_HELIUS_PATH)
    for module in modules:
        for forbidden in _FORBIDDEN_STAGE21_FAKE_ONLY_MODULES:
            assert module != forbidden, (
                f"adapter forbidden Stage 21.2 fake-only import {module!r}"
            )


# ---------------------------------------------------------------------------
# Adapter env-read boundary
# ---------------------------------------------------------------------------


def test_adapter_does_not_read_environ_directly():
    assert not _module_reads_env(PROVIDER_ADAPTER_HELIUS_PATH), (
        "provider_adapter_helius.py must not read os.environ / "
        "os.getenv -- the Stage 21 env-read boundary stays at "
        "config.py alone"
    )


# ---------------------------------------------------------------------------
# Adapter top-level side-effect freedom
# ---------------------------------------------------------------------------


def test_adapter_top_level_is_side_effect_free():
    """Adapter top-level statements are restricted to declarations.

    Mirrors
    ``test_import_boundaries.test_no_top_level_network_side_effect_on_import``;
    re-pinned here for 21.3B so a future drift surfaces here as
    well as in the global test.
    """
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
    source = _read_source(PROVIDER_ADAPTER_HELIUS_PATH)
    tree = ast.parse(source)
    for node in tree.body:
        assert isinstance(node, allowed_top_level), (
            f"provider_adapter_helius.py: unexpected top-level node "
            f"{type(node).__name__}"
        )


def test_adapter_import_does_not_open_sockets_or_files():
    """Importing the adapter is purely declarative.

    The check is structural: the AST has no top-level Call /
    With / For / While node. The combination of this test and
    ``test_adapter_top_level_is_side_effect_free`` pins the
    side-effect-freedom invariant.
    """
    source = _read_source(PROVIDER_ADAPTER_HELIUS_PATH)
    tree = ast.parse(source)
    for node in tree.body:
        assert not isinstance(node, (ast.Call, ast.With, ast.For, ast.While)), (
            f"provider_adapter_helius.py top-level node "
            f"{type(node).__name__} is not declarative"
        )


# Audit-21.3B Minor 1 hardening: scan the adapter AST for
# forbidden Call func names anywhere at module top level,
# including inside assignments / If / Try / Expr / etc. The
# earlier ``test_adapter_top_level_is_side_effect_free`` checks
# only the type of each top-level statement node, so a future
# drift like ``X = open("config")`` would not be caught by that
# test alone. This deeper AST scan catches it.


# Forbidden Call func names. Substring match on the rightmost
# attribute name is intentional so ``requests.get(...)`` /
# ``httpx.post(...)`` / ``aiohttp.ClientSession(...)`` all trip
# the check via their leftmost name component.
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
)


class _TopLevelCallCollector(ast.NodeVisitor):
    """AST visitor that collects every Call node outside function/class scopes.

    The visitor increments a depth counter on
    ``FunctionDef`` / ``AsyncFunctionDef`` / ``ClassDef`` entry
    and decrements on exit; only Call nodes seen at depth 0 are
    collected. This catches top-level constructs like
    ``X = open(...)`` while ignoring calls inside function /
    class bodies (those are deferred until the function /
    class is invoked).
    """

    def __init__(self) -> None:
        self.depth = 0
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
    """Return all identifier components from top-level Call func nodes.

    For each collected Call, both the leftmost ``Name`` and
    every ``Attribute.attr`` along the dotted chain are added.
    A call like ``requests.sessions.Session().get(...)`` would
    contribute ``{"requests", "sessions", "Session", "get"}``.
    """
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


def test_adapter_top_level_does_not_call_forbidden_io():
    """Top-level adapter source has no Call to open / socket / urlopen / etc.

    Catches a future drift that introduces an import-time
    side effect, e.g.::

        _CACHED_CLIENT = open("config.json")
        _CONNECTION = socket.socket()
        _BASE_URL = requests.get(...)

    The scan walks the AST and ignores calls inside function /
    class bodies (those are deferred).
    """
    source = _read_source(PROVIDER_ADAPTER_HELIUS_PATH)
    names = _collect_top_level_call_names(source)
    leaked = set()
    for forbidden in _FORBIDDEN_TOP_LEVEL_CALL_NAMES:
        if forbidden in names:
            leaked.add(forbidden)
    assert not leaked, (
        "provider_adapter_helius.py top-level executes forbidden "
        f"I/O calls: {sorted(leaked)}"
    )


def test_top_level_call_collector_negative_fixture_catches_open_assignment():
    """Self-test: a synthetic ``X = open(...)`` at module top level trips."""
    synthetic = (
        '"""docstring."""\n'
        "from pathlib import Path\n"
        "X = open('/dev/null')\n"
    )
    names = _collect_top_level_call_names(synthetic)
    assert "open" in names


def test_top_level_call_collector_negative_fixture_catches_attribute_call():
    """Self-test: a synthetic ``requests.get(...)`` at module top level trips."""
    synthetic = (
        '"""docstring."""\n'
        "import requests\n"
        "X = requests.get('about:blank')\n"
    )
    names = _collect_top_level_call_names(synthetic)
    assert "requests" in names
    assert "get" in names


def test_top_level_call_collector_ignores_calls_inside_function_bodies():
    """Self-test: a call inside a function body must NOT be collected."""
    synthetic = (
        '"""docstring."""\n'
        "def fetch():\n"
        "    return open('/dev/null')\n"
    )
    names = _collect_top_level_call_names(synthetic)
    assert "open" not in names


def test_top_level_call_collector_ignores_calls_inside_class_bodies():
    """Self-test: a call inside a method body must NOT be collected."""
    synthetic = (
        '"""docstring."""\n'
        "class X:\n"
        "    def fetch(self):\n"
        "        return socket.socket()\n"
    )
    names = _collect_top_level_call_names(synthetic)
    assert "socket" not in names


# ---------------------------------------------------------------------------
# Forbidden symbol vocabulary
# ---------------------------------------------------------------------------


def test_adapter_has_no_forbidden_identifier_substrings():
    """No retry / backoff / dedupe / archive / Discord / runner symbol.

    Scans every identifier position (Names / Attributes /
    FunctionDef / ClassDef / args / aliases). Strings inside
    docstrings or string literals are NOT scanned -- the
    adapter's docstring mentions "no retry / backoff / dedupe"
    as a scope note, and that mention is correct.
    """
    source = _read_source(PROVIDER_ADAPTER_HELIUS_PATH)
    idents = _extract_all_identifiers(source)
    for ident in idents:
        lower = ident.lower()
        for forbidden in _FORBIDDEN_ADAPTER_IDENTIFIER_SUBSTRINGS:
            assert forbidden not in lower, (
                f"adapter identifier {ident!r} contains forbidden "
                f"substring {forbidden!r}"
            )


def test_adapter_has_no_forbidden_named_definitions():
    """No send / dispatch / publish / transmit definitions.

    These tokens are commonly part of larger names (e.g.
    ``transport_target`` includes ``transport``); the
    substring scan above catches the broader category. This
    check pins the narrower rule: the adapter does not DEFINE
    any function / class / top-level binding whose name
    contains one of these verbs.
    """
    source = _read_source(PROVIDER_ADAPTER_HELIUS_PATH)
    defined = _extract_defined_identifiers(source)
    for name in defined:
        lower = name.lower()
        for forbidden in _FORBIDDEN_ADAPTER_NAMED_DEFINITIONS:
            assert forbidden not in lower, (
                f"adapter defines forbidden symbol {name!r} containing "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


def test_adapter_source_contains_no_url_literals():
    source = _read_source(PROVIDER_ADAPTER_HELIUS_PATH)
    assert "https://" not in source, (
        "provider_adapter_helius.py: forbidden 'https://' literal"
    )
    assert "wss://" not in source, (
        "provider_adapter_helius.py: forbidden 'wss://' literal"
    )


def test_adapter_source_contains_no_bot_db_reference():
    source = _read_source(PROVIDER_ADAPTER_HELIUS_PATH)
    assert "bot.db" not in source, (
        "provider_adapter_helius.py: forbidden 'bot.db' reference"
    )


# ---------------------------------------------------------------------------
# Locked vocabulary
# ---------------------------------------------------------------------------


def test_adapter_locked_provider_name_is_helius():
    assert HELIUS_PROVIDER_NAME == "helius"


def test_adapter_locked_chain_is_solana_mainnet():
    assert HELIUS_CHAIN_NAME == "solana_mainnet"


def test_adapter_locked_source_kind_is_helius_grpc_compatible():
    # The label is intentionally generic so the same adapter
    # boundary handles Helius enhanced-webhook AND Helius
    # gRPC-compatible feeds without locking the architecture
    # into HTTP polling.
    assert HELIUS_SOURCE_KIND == "helius_grpc_compatible"


def test_adapter_locked_instruction_kind_is_still_placeholder():
    # Stage 21.3B keeps the decoder vocabulary at the Stage
    # 21.3A placeholder. The real instruction-kind vocabulary
    # is deferred -- introducing a new value here is an
    # explicit operator decision paired with a decoder update.
    assert HELIUS_INSTRUCTION_KIND_PLACEHOLDER == "reserved_for_21_3b"


def test_adapter_locked_values_set_size_is_exactly_four():
    assert len(HELIUS_ADAPTER_LOCKED_VALUES) == 4


def test_required_client_response_keys_locked_to_seven_keys():
    # The seven keys the adapter requires from the injected
    # client. Drifting this list is an explicit operator
    # decision -- the adapter is the boundary between the
    # client and the decoder.
    assert REQUIRED_CLIENT_RESPONSE_KEYS == (
        "provider_event_id",
        "signature",
        "slot",
        "observed_at_utc",
        "event_type",
        "mint",
        "decoded_fields",
    )


# ---------------------------------------------------------------------------
# Cross-module invariants the adapter must not violate
# ---------------------------------------------------------------------------


def test_decoder_supported_instruction_kinds_not_widened_by_21_3b():
    # Stage 21.3B must not silently widen the decoder
    # vocabulary. The decoder still accepts only the
    # placeholder; the adapter pins its emitted
    # instruction_kind to that placeholder.
    assert SUPPORTED_INSTRUCTION_KINDS == frozenset({"reserved_for_21_3b"})


def test_live_readiness_placeholder_provider_id_is_unchanged_by_21_3b():
    # Stage 21.3B does NOT lift the live-readiness
    # placeholder. The readiness gate accepts only the
    # placeholder until Stage 21.4 (live runner) lifts it
    # in a paired update with the readiness reason-set.
    assert PLACEHOLDER_PROVIDER_ID_21_3B == "reserved_for_21_3b"


# ---------------------------------------------------------------------------
# Error hierarchy invariants
# ---------------------------------------------------------------------------


def test_adapter_error_hierarchy_is_module_local_not_stage21_error():
    # Mirrors the Stage 21.3A decoder's Q3 decision -- the
    # adapter error hierarchy is module-local and rooted at
    # plain Exception, not Stage21Error. The closed E2120..E2122
    # codes stay reserved for a future adapter contract
    # surface that wants to integrate with the central
    # registry.
    from PHX2.stage21.errors import Stage21Error

    assert issubclass(HeliusAdapterError, Exception)
    assert not issubclass(HeliusAdapterError, Stage21Error)
