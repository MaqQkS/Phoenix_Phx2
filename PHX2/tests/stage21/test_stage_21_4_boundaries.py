"""Stage 21.4 boundary / scope tests.

Pins the Stage 21.4 scope at the file / import / vocabulary
level. Complementary to the global Stage 21 boundary tests
(``test_import_boundaries.py`` / ``test_env_read_boundaries.py``
/ ``test_no_public_routing.py`` / ``test_no_secret_leaks.py``)
that scan every Stage 21 production module. This file pins the
21.4 specifics:

  * ``private_smoke_runner.py`` exists.
  * Forbidden 21.4 file set (retry / backoff / dedupe / archive /
    quarantine / scheduler / daemon / orchestrator / manifest /
    public-dispatcher / subscriber-dispatcher / paid-dispatcher /
    live_run_loop) remains absent.
  * The runner module does NOT import any network / RPC /
    messaging / HTTP / DB / scheduler / secrets-management
    library.
  * The runner module does NOT import Phoenix1, any prior
    Stage 17..20 runtime, any PHX2 runtime layer, the Stage
    21.2 fake-path modules, or the Stage 21.3B Helius adapter
    directly (the runner depends on its own
    ``Stage21ProviderAdapter`` Protocol).
  * The runner module does NOT read ``os.environ`` /
    ``os.getenv``.
  * The runner module's top-level is side-effect-free.
  * The runner module's identifier vocabulary does NOT
    introduce any retry / backoff / dedupe / archive /
    quarantine / scheduler / daemon / orchestrator /
    subscriber / paid_dispatch / telegram / axiom / jito /
    eligibility symbol -- those concerns belong to Stage 22 /
    later / never.
  * The runner module source contains NO raw URL literal.
  * The runner module pins ``STAGE21_4_SKIPPED_REASONS`` to
    its locked closed set.
  * The runner does NOT construct ``HeliusProviderAdapter`` or
    ``DiscordPrivateTransport`` -- both come in via dependency
    injection.
  * The 21.4 scope introduces NO ``stage21_live`` marker and
    NO env-gated real-send code path.

The ``runner`` / ``smoke`` / ``private`` substrings are
EXPLICITLY allowed in identifier names that belong to this
module (e.g. ``private_smoke_runner`` /
``run_one_private_smoke_ping`` / ``Stage21RunnerError``).
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage21.private_smoke_runner import (
    DEFAULT_MAX_EVENTS,
    SKIPPED_REASON_PROVIDER_FETCH_FAILED,
    SKIPPED_REASON_PROVIDER_RETURNED_TOO_MANY,
    SKIPPED_REASON_PROVIDER_RETURNED_ZERO_EVENTS,
    SKIPPED_REASON_READINESS_NOT_READY,
    STAGE21_4_SKIPPED_REASONS,
    STAGE21_4_SMOKE_LABEL,
    Stage21PrivateSmokeResult,
    Stage21ProviderAdapter,
    Stage21RunnerError,
)


STAGE21_ROOT: Path = Path(__file__).parent.parent.parent / "stage21"
TESTS_STAGE21_ROOT: Path = Path(__file__).parent

PRIVATE_SMOKE_RUNNER_PATH: Path = (
    STAGE21_ROOT / "private_smoke_runner.py"
)


# Stage 21.4 forbidden production filenames. Each covers a
# concern that belongs to Stage 22 or strictly later.
_FORBIDDEN_21_4_FILE_NAMES: tuple[str, ...] = (
    "retry.py",
    "backoff.py",
    "dedupe.py",
    "archive.py",
    "quarantine.py",
    "scheduler.py",
    "daemon.py",
    "orchestrator.py",
    "live_run_loop.py",
    "subscriber_dispatcher.py",
    "public_dispatcher.py",
    "paid_dispatcher.py",
    "stage21_4_manifest.py",
    "stage21_3_manifest.py",
)


# Forbidden runtime / messaging / network / DB / scheduler /
# secrets-management library imports. The runner depends on its
# own Protocol and accepts the adapter / transport via injection
# so it has zero need for any of these libraries.
_FORBIDDEN_IMPORT_MODULE_PATTERNS: tuple[str, ...] = (
    # Network / RPC / HTTP
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "urllib.request",
    "http.client",
    "socket",
    "websockets",
    "grpc",
    "grpcio",
    # Provider client packages
    "helius",
    "birdeye",
    "dexscreener",
    "jupiter",
    "jito",
    # Messaging / webhook libraries
    "discord.py",
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


# The runner must depend on its own ``Stage21ProviderAdapter``
# Protocol, NOT on the Stage 21.3B Helius adapter directly. It
# must NOT import the Stage 21.2 fake provider / fake transport
# / live-path simulator modules either; those are the fake-path
# boundary, distinct from the live runner.
_FORBIDDEN_STAGE21_NEIGHBOUR_MODULES: tuple[str, ...] = (
    "PHX2.stage21.fake_provider",
    "PHX2.stage21.fake_transport",
    "PHX2.stage21.live_path_simulator",
    "PHX2.stage21.provider_adapter_helius",
)


# Identifier-position substrings the runner source MUST NOT
# define. These are concerns that belong to strictly later
# stages: retry / backoff / dedupe / archive / quarantine
# (Stage 22), scheduler / daemon / orchestrator (long-running
# infra), and forever-forbidden routing / wrong-stage concerns.
#
# ``runner`` / ``smoke`` / ``private`` are EXPLICITLY NOT on
# this list -- they are the legitimate vocabulary of the 21.4
# runner module.
#
# ``public_dispatch`` is NOT on this list either: the runner
# constructs a ``TransportPayload`` with the locked
# ``safe_for_public_dispatch=False`` kwarg, which is the
# whitelisted invariant identifier across Stage 21. The global
# ``test_no_public_routing.py`` scanner enforces that
# ``public_dispatch`` as a stand-alone or compound identifier
# remains forbidden tree-wide; the 21.4 boundary test does NOT
# duplicate that check (and a duplicated substring scan here
# would false-positive on the whitelisted invariant).
_FORBIDDEN_RUNNER_IDENTIFIER_SUBSTRINGS: tuple[str, ...] = (
    "retry",
    "backoff",
    "dedupe",
    "archive",
    "quarantine",
    "ratelimit",
    "rate_limit",
    "scheduler",
    "orchestrator",
    "subscriber",
    "paid_dispatch",
    "paid_channel",
    "paid_signal",
    "telegram",
    "axiom",
    "jito",
    "eligibility",
)


# URL-shaped substrings the runner source MUST NOT contain.
# The runner has no real HTTP client and no need for any URL
# literal; the injected client owns every URL.
_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "https://",
    "http://",
    "wss://",
    "discord.com",
    "discordapp.com",
    "hooks.slack.com",
)


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_imported_module_paths(path: Path) -> set[str]:
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


class _TopLevelCallCollector(ast.NodeVisitor):
    """Collect every Call node outside any function or class body."""

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


def _collect_call_names_anywhere(source: str) -> list[str]:
    """Return every call-site callable name (Name or Attribute terminal).

    Used to assert the runner does NOT construct specific concrete
    classes anywhere in the module.
    """
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.append(func.id)
            elif isinstance(func, ast.Attribute):
                names.append(func.attr)
    return names


def _file_registers_live_marker(path: Path) -> bool:
    """Return True iff ``path`` registers a ``stage21_live`` pytest marker."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "stage21_live":
            return True
    return False


# ---------------------------------------------------------------------------
# File scope
# ---------------------------------------------------------------------------


def test_private_smoke_runner_module_exists():
    assert PRIVATE_SMOKE_RUNNER_PATH.exists(), (
        "Stage 21.4 requires PHX2/stage21/private_smoke_runner.py"
    )


def test_forbidden_21_4_production_files_do_not_exist():
    for filename in _FORBIDDEN_21_4_FILE_NAMES:
        path = STAGE21_ROOT / filename
        assert not path.exists(), (
            f"Stage 21.4 scope violation: {filename} must not exist"
        )


# ---------------------------------------------------------------------------
# Import scope
# ---------------------------------------------------------------------------


def test_runner_does_not_import_forbidden_runtime_libs():
    modules = _collect_imported_module_paths(PRIVATE_SMOKE_RUNNER_PATH)
    for module in modules:
        lower = module.lower()
        for pattern in _FORBIDDEN_IMPORT_MODULE_PATTERNS:
            assert pattern not in lower, (
                f"private_smoke_runner.py imports forbidden runtime "
                f"module pattern {pattern!r} via {module!r}"
            )


def test_runner_does_not_import_prior_stage_or_phoenix1():
    modules = _collect_imported_module_paths(PRIVATE_SMOKE_RUNNER_PATH)
    for module in modules:
        assert not module.startswith("phoenix1"), (
            f"runner forbidden phoenix1 import {module!r}"
        )
        for prefix in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
            assert not module.startswith(prefix), (
                f"runner forbidden prior-stage import {module!r}"
            )


def test_runner_does_not_import_phx2_runtime_layer():
    modules = _collect_imported_module_paths(PRIVATE_SMOKE_RUNNER_PATH)
    for module in modules:
        for prefix in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
            assert not module.startswith(prefix), (
                f"runner forbidden PHX2 runtime-layer import {module!r}"
            )


def test_runner_does_not_import_fake_path_or_helius_adapter():
    """Runner must not import fake-path modules or the Helius adapter.

    The runner depends on its own ``Stage21ProviderAdapter``
    Protocol. The Stage 21.3B ``HeliusProviderAdapter`` satisfies
    that Protocol structurally and is injected by the caller;
    the runner does not import the concrete class.
    """
    modules = _collect_imported_module_paths(PRIVATE_SMOKE_RUNNER_PATH)
    for module in modules:
        for forbidden in _FORBIDDEN_STAGE21_NEIGHBOUR_MODULES:
            assert module != forbidden, (
                f"runner forbidden Stage 21 neighbour import {module!r}"
            )


# ---------------------------------------------------------------------------
# Env-read boundary
# ---------------------------------------------------------------------------


def test_runner_does_not_read_environ_directly():
    assert not _module_reads_env(PRIVATE_SMOKE_RUNNER_PATH), (
        "private_smoke_runner.py must not read os.environ / "
        "os.getenv -- the Stage 21 env-read boundary stays at "
        "config.py alone"
    )


# ---------------------------------------------------------------------------
# Top-level side-effect freedom
# ---------------------------------------------------------------------------


def test_runner_top_level_is_side_effect_free():
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
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    for node in tree.body:
        assert isinstance(node, allowed_top_level), (
            f"private_smoke_runner.py: unexpected top-level node "
            f"{type(node).__name__}"
        )


def test_runner_top_level_has_no_open_socket_or_io_call():
    forbidden_call_names: tuple[str, ...] = (
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
    )
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    names = _collect_top_level_call_names(source)
    leaked: set[str] = set()
    for forbidden in forbidden_call_names:
        if forbidden in names:
            leaked.add(forbidden)
    assert not leaked, (
        "private_smoke_runner.py top-level executes forbidden "
        f"I/O calls: {sorted(leaked)}"
    )


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


def test_runner_source_contains_no_url_literals():
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
        assert needle not in source, (
            f"private_smoke_runner.py: forbidden URL literal "
            f"{needle!r} found in source"
        )


def test_runner_source_contains_no_bot_db_reference():
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    assert "bot.db" not in source


# ---------------------------------------------------------------------------
# Forbidden identifier vocabulary (Stage 22+ concerns)
# ---------------------------------------------------------------------------


def test_runner_has_no_forbidden_identifier_substrings():
    """No retry / backoff / dedupe / archive / quarantine / scheduler / etc.

    Substring scan over identifier-position names only. String
    literals (including docstrings) are NOT scanned.
    """
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    idents = _extract_all_identifiers(source)
    for ident in idents:
        lower = ident.lower()
        for forbidden in _FORBIDDEN_RUNNER_IDENTIFIER_SUBSTRINGS:
            assert forbidden not in lower, (
                f"runner identifier {ident!r} contains forbidden "
                f"substring {forbidden!r}"
            )


def test_runner_does_not_define_forbidden_scope_classes_or_funcs():
    """No top-level def / class with a forbidden-scope name."""
    forbidden_named_defs: tuple[str, ...] = (
        "Scheduler",
        "Daemon",
        "Orchestrator",
        "RetryPolicy",
        "BackoffPolicy",
        "Dedupe",
        "Archive",
        "Quarantine",
        "PublicDispatch",
        "SubscriberDispatch",
        "PaidDispatch",
    )
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            assert node.name not in forbidden_named_defs, (
                f"runner defines forbidden scope symbol {node.name!r}"
            )


# ---------------------------------------------------------------------------
# No real-client construction inside the runner
# ---------------------------------------------------------------------------


def test_runner_does_not_construct_helius_provider_adapter():
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    names = _collect_call_names_anywhere(source)
    assert "HeliusProviderAdapter" not in names, (
        "private_smoke_runner.py must not construct HeliusProviderAdapter "
        "directly -- the runner depends on the Stage21ProviderAdapter "
        "Protocol and accepts the adapter via dependency injection"
    )


def test_runner_does_not_construct_discord_private_transport():
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    names = _collect_call_names_anywhere(source)
    assert "DiscordPrivateTransport" not in names, (
        "private_smoke_runner.py must not construct DiscordPrivateTransport "
        "directly -- the runner accepts the transport via dependency "
        "injection"
    )


# ---------------------------------------------------------------------------
# Locked closed-set skipped-reason vocabulary
# ---------------------------------------------------------------------------


def test_skipped_reason_set_matches_locked_four_tokens_exactly():
    assert STAGE21_4_SKIPPED_REASONS == (
        SKIPPED_REASON_READINESS_NOT_READY,
        SKIPPED_REASON_PROVIDER_FETCH_FAILED,
        SKIPPED_REASON_PROVIDER_RETURNED_ZERO_EVENTS,
        SKIPPED_REASON_PROVIDER_RETURNED_TOO_MANY,
    )
    assert len(STAGE21_4_SKIPPED_REASONS) == 4
    assert len(set(STAGE21_4_SKIPPED_REASONS)) == 4


def test_skipped_reason_tokens_are_non_secret_strings():
    for token in STAGE21_4_SKIPPED_REASONS:
        assert isinstance(token, str)
        assert token == token.strip()
        assert all(
            c.islower() or c.isdigit() or c == "_" for c in token
        ), token
        assert len(token) <= 64


def test_smoke_label_is_locked_to_21_4():
    assert STAGE21_4_SMOKE_LABEL == "21.4"


def test_default_max_events_is_locked_to_one():
    assert DEFAULT_MAX_EVENTS == 1


# ---------------------------------------------------------------------------
# Error hierarchy is module-local (mirrors 21.3A / 21.3B / 21.3C)
# ---------------------------------------------------------------------------


def test_runner_error_is_module_local_not_stage21_error():
    from PHX2.stage21.errors import Stage21Error

    assert issubclass(Stage21RunnerError, Exception)
    assert not issubclass(Stage21RunnerError, Stage21Error)


# ---------------------------------------------------------------------------
# run_one_private_smoke_ping signature is keyword-only
# ---------------------------------------------------------------------------


def test_run_one_private_smoke_ping_signature_is_keyword_only():
    """All positional parameters are kwonly.

    Pins the call surface: every parameter on the public entry
    point must be passed by keyword. This prevents an accidental
    ordering drift (e.g. recipient and readiness swapped) from
    causing a silent misroute.
    """
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "run_one_private_smoke_ping"
        ):
            found = True
            args = node.args
            positional = [a.arg for a in args.args]
            kwonly = [a.arg for a in args.kwonlyargs]
            assert positional == [], (
                f"run_one_private_smoke_ping positional args: {positional!r}"
            )
            assert set(kwonly) == {
                "provider_adapter",
                "transport",
                "readiness",
                "recipient",
                "max_events",
                "cursor",
            }, f"run_one_private_smoke_ping kwonly args: {kwonly!r}"
    assert found, (
        "run_one_private_smoke_ping not found in private_smoke_runner.py"
    )


def test_run_one_private_smoke_ping_returns_stage21_private_smoke_result():
    """The public entry point's return annotation is the locked result type."""
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "run_one_private_smoke_ping"
        ):
            found = True
            returns = node.returns
            assert returns is not None, (
                "run_one_private_smoke_ping must declare a return annotation"
            )
            assert isinstance(returns, ast.Name), (
                f"return annotation should be a Name, got "
                f"{type(returns).__name__}"
            )
            assert returns.id == "Stage21PrivateSmokeResult", (
                f"run_one_private_smoke_ping returns {returns.id!r}, "
                "expected 'Stage21PrivateSmokeResult'"
            )
    assert found


# ---------------------------------------------------------------------------
# Stage21ProviderAdapter Protocol pin
# ---------------------------------------------------------------------------


def test_provider_adapter_protocol_method_signature_is_kwonly():
    """``fetch_normalized_events`` requires kwonly ``cursor`` + ``max_results``.

    Pins the Protocol surface so a future drift that renames the
    method or changes its kwonly signature fails here.
    """
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "Stage21ProviderAdapter"
        ):
            for item in node.body:
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == "fetch_normalized_events"
                ):
                    found = True
                    args = item.args
                    positional = [a.arg for a in args.args]
                    kwonly = [a.arg for a in args.kwonlyargs]
                    assert positional == ["self"]
                    assert set(kwonly) == {"cursor", "max_results"}, (
                        f"fetch_normalized_events kwonly args: {kwonly!r}"
                    )
    assert found, (
        "Stage21ProviderAdapter.fetch_normalized_events not found"
    )


def test_stage21_provider_adapter_is_a_protocol():
    """The injected-adapter contract is a Protocol, not a concrete class."""
    # ``typing.runtime_checkable`` is not required; structural
    # conformance at the call site is enough. The presence of
    # ``_is_protocol`` (a CPython internal flag) is the cheapest
    # asserting hook; otherwise we rely on the Protocol base in
    # the source AST.
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "Stage21ProviderAdapter"
        ):
            found = True
            base_names: set[str] = set()
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_names.add(base.id)
                elif isinstance(base, ast.Attribute):
                    base_names.add(base.attr)
            assert "Protocol" in base_names, (
                f"Stage21ProviderAdapter bases: {base_names!r}; expected "
                "to subclass typing.Protocol"
            )
    assert found, "Stage21ProviderAdapter not found in source"


# ---------------------------------------------------------------------------
# Stage21PrivateSmokeResult NamedTuple shape
# ---------------------------------------------------------------------------


def test_result_record_field_names_are_locked():
    """Pin the seven NamedTuple field names so a drift surfaces here."""
    assert Stage21PrivateSmokeResult._fields == (
        "attempted",
        "sent",
        "skipped_reason",
        "transport_reason",
        "provider_event_count",
        "normalized_event_id",
        "recipient",
    )


# ---------------------------------------------------------------------------
# Live-test marker boundary (Stage 21.4 stays offline-only)
# ---------------------------------------------------------------------------


def test_no_live_marker_in_runner_production_source():
    assert not _file_registers_live_marker(PRIVATE_SMOKE_RUNNER_PATH), (
        "Stage 21.4 must not introduce a 'stage21_live' marker; the "
        "first live smoke ping is operator-driven, not test-driven"
    )


def test_no_live_marker_in_runner_offline_test():
    offline_test_path = (
        TESTS_STAGE21_ROOT / "test_private_smoke_runner_offline.py"
    )
    assert not _file_registers_live_marker(offline_test_path), (
        "Stage 21.4 offline test must not use a 'stage21_live' marker"
    )


def test_no_live_marker_in_21_4_boundary_test_itself():
    assert not _file_registers_live_marker(Path(__file__)), (
        "boundary test must not register a 'stage21_live' marker"
    )


# ---------------------------------------------------------------------------
# Sanity: the offline test file uses the in-memory fakes only
# ---------------------------------------------------------------------------


def test_offline_test_does_not_import_real_network_libraries():
    """The offline test must not import requests / httpx / aiohttp / etc."""
    offline_test_path = (
        TESTS_STAGE21_ROOT / "test_private_smoke_runner_offline.py"
    )
    modules = _collect_imported_module_paths(offline_test_path)
    for module in modules:
        lower = module.lower()
        for pattern in (
            "requests",
            "httpx",
            "aiohttp",
            "urllib3",
            "websockets",
            "grpc",
            "discord.py",
            "telegram",
            "telethon",
            "webhook",
            "sqlalchemy",
            "sqlite3",
        ):
            assert pattern not in lower, (
                f"offline test imports forbidden runtime module "
                f"pattern {pattern!r} via {module!r}"
            )


# ---------------------------------------------------------------------------
# Minor-audit hardening: no sleep / no loop / no CLI / no __main__ /
# no file persistence
# ---------------------------------------------------------------------------
#
# Per the Stage 21.4 Codex audit (Minor findings 1 + 2). All
# checks are AST-based against the runner module.


# Top-level module names the runner must NEVER import. The CLI /
# sleep set covers the 21.4 "no CLI surface" decision plus the
# "no time.sleep" rule. The file-persistence set covers the
# "no DB / no manifest / no artifact write" scope. ``sqlite3`` /
# ``sqlalchemy`` are already forbidden by
# ``_FORBIDDEN_IMPORT_MODULE_PATTERNS`` and are not repeated here.
_FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES: frozenset[str] = frozenset({
    "argparse",
    "click",
    "typer",
    "fire",
    "docopt",
    "time",
})


_FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES: frozenset[str] = frozenset({
    "pathlib",
    "os",
    "shutil",
    "tempfile",
    "json",
    "csv",
})


# Callable names the runner must NEVER invoke ANYWHERE in the
# module (top-level or inside any function / class).
# ``Path.write_text`` / ``Path.write_bytes`` / ``os.replace`` /
# ``os.rename`` etc. are caught via their terminal attribute
# names (``write_text`` / ``write_bytes`` / ``replace`` /
# ``rename``); ``_collect_call_names_anywhere`` records the
# terminal callable name for every ``Call`` node regardless of
# whether the callable is a bare ``Name`` or an ``Attribute``.
#
# ``dumps`` is included because the runner has no persistence
# context that legitimately needs it (no idempotency token
# derivation, no manifest write); a future legitimate non-
# persistence use of ``json.dumps`` would have to update this
# locked set explicitly with a justifying comment.
#
# ``replace`` covers ``Path.replace`` / ``os.replace`` /
# ``str.replace``. The runner has no current need for any of
# the three; a future legitimate ``str.replace`` would update
# this set explicitly.
_FORBIDDEN_FILE_PERSISTENCE_CALL_NAMES: frozenset[str] = frozenset({
    "open",
    "write",
    "write_text",
    "write_bytes",
    "writelines",
    "dump",
    "dumps",
    "mkdir",
    "makedirs",
    "touch",
    "remove",
    "unlink",
    "rename",
    "replace",
})


def test_runner_does_not_import_cli_or_sleep_libraries():
    """No argparse / click / typer / fire / docopt / time imports.

    No CLI surface and no ``time.sleep`` means no need for any of
    these libraries. ``time`` is on this list specifically to
    prevent ``time.sleep`` -- a runner that sleeps is by
    definition no longer single-shot.
    """
    modules = _collect_imported_module_paths(PRIVATE_SMOKE_RUNNER_PATH)
    for module in modules:
        top = module.split(".")[0]
        assert top not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES, (
            f"runner imports forbidden CLI / sleep library: {module!r}"
        )


def test_runner_does_not_import_file_persistence_libraries():
    """No pathlib / os / shutil / tempfile / json / csv imports.

    The 21.4 runner returns an in-memory result NamedTuple. No
    DB, no manifest, no artifact file, no ledger persistence. The
    absence of any file-persistence import is the cleanest
    expression of that scope. ``sqlite3`` / ``sqlalchemy`` are
    already forbidden by the broader runtime-import scanner.
    """
    modules = _collect_imported_module_paths(PRIVATE_SMOKE_RUNNER_PATH)
    for module in modules:
        top = module.split(".")[0]
        assert top not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES, (
            "runner imports forbidden file-persistence library: "
            f"{module!r}"
        )


def test_runner_has_no_sleep_call_anywhere():
    """No ``time.sleep`` / bare ``sleep(...)`` / ``asyncio.sleep`` etc.

    The check looks at the terminal callable name of every
    ``Call`` node in the module. It catches both attribute-form
    calls (``time.sleep(1)`` -> terminal attr ``sleep``) and
    bare-name calls (``sleep(1)`` -> func.id ``sleep``).
    """
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    names = _collect_call_names_anywhere(source)
    assert "sleep" not in names, (
        "runner contains a `sleep(...)` call -- a sleeping runner is "
        "no longer single-shot"
    )


def test_runner_has_no_for_loops():
    """No ``for`` loop nodes anywhere in the runner module.

    The runner is single-shot: it forwards exactly one event to
    the transport. There is no batching, no provider-stream
    iteration, no retry loop, no fan-out. The presence of any
    ``for`` node would enable cross-event semantics the 21.4
    scope forbids.
    """
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        assert not isinstance(node, ast.For), (
            "runner contains a `for` loop -- the runner is single-shot "
            "and must not iterate"
        )


def test_runner_has_no_while_loops():
    """No ``while`` loop nodes anywhere in the runner module."""
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        assert not isinstance(node, ast.While), (
            "runner contains a `while` loop -- forbidden by the "
            "single-shot 21.4 scope"
        )


def test_runner_has_no_async_for_loops():
    """No ``async for`` loop nodes anywhere in the runner module."""
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        assert not isinstance(node, ast.AsyncFor), (
            "runner contains an `async for` loop -- forbidden by the "
            "single-shot 21.4 scope"
        )


def test_runner_has_no_dunder_main_guard():
    """No ``if __name__ == '__main__':`` block in the runner.

    The 21.4 runner is library-shaped: an operator scratch script
    imports ``run_one_private_smoke_ping`` and invokes it. A
    ``__main__`` guard would establish a CLI-style entry point,
    which the locked 21.4 scope forbids.

    The check walks every ``ast.Compare`` node in the runner and
    flags any compare whose participants include both a ``Name``
    node ``__name__`` and a string constant ``"__main__"`` (in
    either order). This catches both
    ``if __name__ == "__main__":`` and
    ``if "__main__" == __name__:`` shapes.
    """
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    for node in ast.walk(tree):
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
                "runner contains a `__name__ == '__main__'` guard -- "
                "the 21.4 scope forbids any CLI-style entry point"
            )


def test_runner_does_not_define_cli_entrypoint_function():
    """No top-level ``main`` / ``cli`` / ``entrypoint`` function.

    The 21.4 runner exposes ``run_one_private_smoke_ping`` as its
    sole public callable. A top-level ``main()`` / ``cli()`` /
    ``entrypoint()`` would advertise a CLI shape that the locked
    scope forbids.

    The check inspects only TOP-LEVEL function / async function
    defs; nested helpers named ``main`` inside a test fixture
    elsewhere would not (and do not) appear in the runner
    module's top-level body.
    """
    forbidden_entrypoint_names: frozenset[str] = frozenset({
        "main",
        "cli",
        "entrypoint",
    })
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in forbidden_entrypoint_names, (
                f"runner defines forbidden CLI-style entrypoint "
                f"function {node.name!r}"
            )


def test_runner_has_no_file_persistence_calls_anywhere():
    """No file-persistence call anywhere in the module.

    The runner returns an in-memory ``Stage21PrivateSmokeResult``.
    The locked 21.4 scope forbids any DB write / manifest write /
    artifact write / ledger persistence. This test walks the AST
    for every ``Call`` node's terminal callable name and asserts
    that none of the locked write-shape names appear:

      open / write / write_text / write_bytes / writelines /
      dump / dumps / mkdir / makedirs / touch / remove / unlink /
      rename / replace

    Strictly stronger than the existing top-level-only check
    ``test_runner_top_level_has_no_open_socket_or_io_call``;
    both are kept for defense in depth.
    """
    source = _read_source(PRIVATE_SMOKE_RUNNER_PATH)
    names = _collect_call_names_anywhere(source)
    leaked = sorted(
        set(names) & _FORBIDDEN_FILE_PERSISTENCE_CALL_NAMES
    )
    assert not leaked, (
        f"runner contains forbidden file-persistence call(s): {leaked}"
    )
