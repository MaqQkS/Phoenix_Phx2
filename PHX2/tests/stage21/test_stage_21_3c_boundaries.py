"""Stage 21.3C boundary / scope tests.

Pins the Stage 21.3C scope at the file / import / vocabulary
level. Complementary to the global Stage 21 boundary tests in
``test_import_boundaries.py`` / ``test_env_read_boundaries.py``
/ ``test_no_public_routing.py`` / ``test_no_secret_leaks.py``,
which scan every Stage 21 production module. This file pins the
21.3C specifics:

  * ``discord_private_transport.py`` exists.
  * Forbidden 21.3C file set (runner / orchestrator / live_run
    / retry / backoff / dedupe / archive / stage21_3_manifest)
    remains absent.
  * The transport module does NOT import any network / RPC /
    messaging / HTTP / DB / scheduler / secrets-management
    library.
  * The transport module does NOT import Phoenix1, any prior
    Stage 17..20 runtime, any PHX2 runtime layer, the Stage
    21.2 fake-only modules, or the Stage 21.3B Helius adapter.
  * The transport module does NOT read ``os.environ`` /
    ``os.getenv``.
  * The transport module's top-level is side-effect-free.
  * The transport module's identifier vocabulary does NOT
    introduce any retry / backoff / dedupe / archive / runner /
    orchestrator / scheduler / public / paid / subscriber
    symbol -- those concerns belong to Stage 21.4 / 22 / never.
  * The transport module source contains NO raw URL literals
    (``https://`` / ``http://`` / ``discord.com`` /
    ``discordapp.com`` / ``hooks.slack.com``).
  * The transport module pins ``STAGE21_3C_REJECTION_REASONS``
    to its locked closed set.
  * The transport class satisfies the Stage21Transport
    Protocol.
  * The 21.3C scope introduces NO ``stage21_live`` marker and
    NO env-gated real-send code path.

The ``discord`` substring is EXPLICITLY allowed in identifier
names that belong to this module (e.g. ``DiscordPrivateTransport``
/ ``DiscordWebhookClientProtocol``) and in non-import string
positions (locked rejection-reason values, docstrings). The 21.3C
boundary tests do NOT forbid all ``discord`` occurrences in this
file.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping, Sequence

import pytest

from PHX2.stage21.discord_private_transport import (
    DiscordPostOutcome,
    DiscordPrivateTransport,
    DiscordTransportClientError,
    DiscordTransportError,
    DiscordWebhookClientProtocol,
    REJECTION_REASON_CLIENT_POST_FAILED,
    REJECTION_REASON_DISPATCH_SAFETY_REJECTED,
    REJECTION_REASON_READINESS_NOT_READY,
    REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST,
    REJECTION_REASON_UPSTREAM_NON_2XX,
    REJECTION_REASON_WEBHOOK_NOT_PRESENT,
    STAGE21_3C_REJECTION_REASONS,
)
from PHX2.stage21.transport_contracts import (
    Stage21Transport,
    TransportPayload,
    TransportResult,
)


STAGE21_ROOT: Path = Path(__file__).parent.parent.parent / "stage21"
TESTS_STAGE21_ROOT: Path = Path(__file__).parent

DISCORD_PRIVATE_TRANSPORT_PATH: Path = (
    STAGE21_ROOT / "discord_private_transport.py"
)


# Stage 21.3C forbidden production filenames. Each name covers a
# concern that belongs to a strictly later stage:
#   * stage21_3_manifest.py / runner.py / orchestrator.py /
#     live_run.py   -> Stage 21.4
#   * retry.py / backoff.py / dedupe.py / archive.py -> Stage 22
_FORBIDDEN_21_3C_FILE_NAMES: tuple[str, ...] = (
    "stage21_3_manifest.py",
    "runner.py",
    "orchestrator.py",
    "live_run.py",
    "retry.py",
    "backoff.py",
    "dedupe.py",
    "archive.py",
)


# Forbidden runtime / messaging / network / DB / scheduler /
# secrets-management library imports. ``discord`` and ``webhook``
# are forbidden as IMPORT MODULE PATHS (no real ``discord.py`` or
# ``webhook`` library); identifier names containing those
# substrings are allowed (e.g. ``DiscordPrivateTransport``).
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


# Forbidden prior-stage prefixes. Stage 21.3C must not reach into
# Phoenix1 or any of the Stage 17..20 runtime layers.
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


# The transport module must not cross the Stage 21.2 fake /
# Stage 21.3B provider boundary. The transport is the
# Stage 21.3C boundary between the renderer/dispatcher and the
# future real client; mixing it with the fake producer / fake
# transport / live-path simulator / Helius adapter would defeat
# the boundary.
_FORBIDDEN_STAGE21_NEIGHBOUR_MODULES: tuple[str, ...] = (
    "PHX2.stage21.fake_provider",
    "PHX2.stage21.fake_transport",
    "PHX2.stage21.live_path_simulator",
    "PHX2.stage21.provider_adapter_helius",
)


# Identifier-position substrings the transport source MUST NOT
# define. These are scope concerns that belong to strictly later
# stages: retry / backoff / dedupe / archive (Stage 22), runner
# / orchestrator / scheduler / live_run (Stage 21.4), and the
# forever-forbidden subscriber / public / paid routing.
#
# ``discord`` and ``webhook`` are EXPLICITLY NOT on this list --
# they are the legitimate vocabulary of the 21.3C transport
# (``DiscordPrivateTransport`` / ``DiscordWebhookClientProtocol``
# / ``webhook_ref``).
_FORBIDDEN_TRANSPORT_IDENTIFIER_SUBSTRINGS: tuple[str, ...] = (
    "retry",
    "backoff",
    "dedupe",
    "archive",
    "runner",
    "orchestrator",
    "scheduler",
    "ratelimit",
    "rate_limit",
    "live_run",
    "subscriber",
    "paid_dispatch",
    "paid_channel",
    "paid_signal",
    "public_dispatch",
    "public_channel",
    "public_signal",
)


# URL-shaped substrings the transport source MUST NOT contain.
# The set is broader than the global stage21 URL-literal check
# (which catches only ``https://`` / ``wss://``); 21.3C also
# forbids ``http://``, bare ``discord.com`` / ``discordapp.com``
# host literals, and the ``hooks.slack.com`` example used by
# operators in other contexts. The webhook URL is constructed by
# the injected client from a SecretRef snapshot held outside this
# module; no URL literal should ever appear in the source.
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


# ---------------------------------------------------------------------------
# File scope
# ---------------------------------------------------------------------------


def test_discord_private_transport_module_exists():
    assert DISCORD_PRIVATE_TRANSPORT_PATH.exists(), (
        "Stage 21.3C requires PHX2/stage21/discord_private_transport.py"
    )


def test_forbidden_21_3c_production_files_do_not_exist():
    for filename in _FORBIDDEN_21_3C_FILE_NAMES:
        path = STAGE21_ROOT / filename
        assert not path.exists(), (
            f"Stage 21.3C scope violation: {filename} must not exist"
        )


# ---------------------------------------------------------------------------
# Import scope
# ---------------------------------------------------------------------------


def test_transport_does_not_import_forbidden_runtime_libs():
    modules = _collect_imported_module_paths(
        DISCORD_PRIVATE_TRANSPORT_PATH
    )
    for module in modules:
        lower = module.lower()
        for pattern in _FORBIDDEN_IMPORT_MODULE_PATTERNS:
            assert pattern not in lower, (
                "discord_private_transport.py imports forbidden runtime "
                f"module pattern {pattern!r} via {module!r}"
            )


def test_transport_does_not_import_prior_stage_or_phoenix1():
    modules = _collect_imported_module_paths(
        DISCORD_PRIVATE_TRANSPORT_PATH
    )
    for module in modules:
        assert not module.startswith("phoenix1"), (
            f"transport forbidden phoenix1 import {module!r}"
        )
        for prefix in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
            assert not module.startswith(prefix), (
                f"transport forbidden prior-stage import {module!r}"
            )


def test_transport_does_not_import_phx2_runtime_layer():
    modules = _collect_imported_module_paths(
        DISCORD_PRIVATE_TRANSPORT_PATH
    )
    for module in modules:
        for prefix in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
            assert not module.startswith(prefix), (
                f"transport forbidden PHX2 runtime-layer import {module!r}"
            )


def test_transport_does_not_import_stage21_neighbour_boundary_modules():
    """Transport must not import Stage 21.2 fakes or the Helius adapter."""
    modules = _collect_imported_module_paths(
        DISCORD_PRIVATE_TRANSPORT_PATH
    )
    for module in modules:
        for forbidden in _FORBIDDEN_STAGE21_NEIGHBOUR_MODULES:
            assert module != forbidden, (
                f"transport forbidden Stage 21 neighbour import {module!r}"
            )


# ---------------------------------------------------------------------------
# Env-read boundary
# ---------------------------------------------------------------------------


def test_transport_does_not_read_environ_directly():
    assert not _module_reads_env(DISCORD_PRIVATE_TRANSPORT_PATH), (
        "discord_private_transport.py must not read os.environ / "
        "os.getenv -- the Stage 21 env-read boundary stays at "
        "config.py alone"
    )


# ---------------------------------------------------------------------------
# Top-level side-effect freedom
# ---------------------------------------------------------------------------


def test_transport_top_level_is_side_effect_free():
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
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    tree = ast.parse(source)
    for node in tree.body:
        assert isinstance(node, allowed_top_level), (
            f"discord_private_transport.py: unexpected top-level node "
            f"{type(node).__name__}"
        )


def test_transport_top_level_has_no_open_socket_or_io_call():
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
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    names = _collect_top_level_call_names(source)
    leaked = set()
    for forbidden in forbidden_call_names:
        if forbidden in names:
            leaked.add(forbidden)
    assert not leaked, (
        "discord_private_transport.py top-level executes forbidden "
        f"I/O calls: {sorted(leaked)}"
    )


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


def test_transport_source_contains_no_url_literals():
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
        assert needle not in source, (
            f"discord_private_transport.py: forbidden URL literal "
            f"{needle!r} found in source"
        )


def test_transport_source_contains_no_bot_db_reference():
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    assert "bot.db" not in source


# ---------------------------------------------------------------------------
# Forbidden identifier vocabulary
# ---------------------------------------------------------------------------


def test_transport_has_no_forbidden_identifier_substrings():
    """No retry / backoff / dedupe / archive / runner / public_dispatch / etc.

    Substring scan over identifier-position names only (the AST
    extractor explicitly skips string literals and docstrings).
    The ``discord`` substring is allowed throughout the module
    by virtue of NOT being on the forbidden list.
    """
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    idents = _extract_all_identifiers(source)
    for ident in idents:
        lower = ident.lower()
        for forbidden in _FORBIDDEN_TRANSPORT_IDENTIFIER_SUBSTRINGS:
            assert forbidden not in lower, (
                f"transport identifier {ident!r} contains forbidden "
                f"substring {forbidden!r}"
            )


def test_transport_does_not_define_forbidden_scope_classes_or_funcs():
    """No top-level def / class with a forbidden-scope name."""
    forbidden_named_defs: tuple[str, ...] = (
        "Runner",
        "Orchestrator",
        "Scheduler",
        "RetryPolicy",
        "BackoffPolicy",
        "Dedupe",
        "Archive",
        "PublicDispatch",
        "SubscriberDispatch",
        "PaidDispatch",
    )
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            assert node.name not in forbidden_named_defs, (
                f"transport defines forbidden scope symbol {node.name!r}"
            )


# ---------------------------------------------------------------------------
# Locked closed-set rejection vocabulary
# ---------------------------------------------------------------------------


def test_rejection_reason_set_matches_locked_six_tokens_exactly():
    assert STAGE21_3C_REJECTION_REASONS == (
        REJECTION_REASON_READINESS_NOT_READY,
        REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST,
        REJECTION_REASON_DISPATCH_SAFETY_REJECTED,
        REJECTION_REASON_WEBHOOK_NOT_PRESENT,
        REJECTION_REASON_CLIENT_POST_FAILED,
        REJECTION_REASON_UPSTREAM_NON_2XX,
    )
    assert len(STAGE21_3C_REJECTION_REASONS) == 6
    assert len(set(STAGE21_3C_REJECTION_REASONS)) == 6


def test_rejection_reason_tokens_are_non_secret_strings():
    """Every reason token is a short snake_case identifier."""
    for token in STAGE21_3C_REJECTION_REASONS:
        assert isinstance(token, str)
        assert token == token.strip()
        assert token.islower() or all(
            c.islower() or c.isdigit() or c == "_" for c in token
        )
        assert len(token) <= 64


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class _ProtoConformanceFakeClient:
    """Minimal client for protocol-conformance smoke check."""

    def post_webhook(
        self,
        *,
        body_text: str,
        idempotency_token: str,
    ) -> DiscordPostOutcome:
        return DiscordPostOutcome(
            accepted=True,
            status_class="2xx",
            upstream_error_type="",
        )


def test_transport_class_satisfies_stage21_transport_protocol_signature():
    """Static structural assignment to ``Stage21Transport`` succeeds.

    The Stage21Transport Protocol requires a ``send`` method
    taking a ``TransportPayload`` and returning a
    ``TransportResult``. The boundary check pins the structural
    typing: any future drift that renames ``send`` or changes
    its signature would fail here.
    """
    from PHX2.stage21.allowlist import build_allowlist_from_sequence
    from PHX2.stage21.live_secrets_boundary import (
        load_live_readiness_config_from_env,
    )
    from PHX2.stage21.secret_redaction import build_secret_ref
    from PHX2.stage21.constants import ENV_VAR_DISCORD_WEBHOOK_URL

    transport = DiscordPrivateTransport(
        client=_ProtoConformanceFakeClient(),
        readiness=load_live_readiness_config_from_env({}),
        webhook_ref=build_secret_ref(
            ENV_VAR_DISCORD_WEBHOOK_URL, "fake-webhook-for-tests"
        ),
        allowlist=build_allowlist_from_sequence(["x"]),
    )
    typed: Stage21Transport = transport
    assert callable(getattr(typed, "send", None))


def test_transport_send_signature_accepts_transport_payload_only():
    """``send`` takes a single positional ``TransportPayload`` argument.

    The boundary test pins the call surface: no extra
    ``webhook_url`` / ``token`` / ``recipient`` positional
    parameter has been introduced.
    """
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "DiscordPrivateTransport":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "send":
                    found = True
                    args = item.args
                    # one positional self, one positional payload
                    positional_arg_names = [a.arg for a in args.args]
                    assert positional_arg_names == ["self", "payload"], (
                        f"DiscordPrivateTransport.send args {positional_arg_names!r}"
                    )
                    assert not args.kwonlyargs, (
                        "DiscordPrivateTransport.send must not have kwonly args"
                    )
    assert found, "DiscordPrivateTransport.send not found in source"


def test_client_protocol_post_webhook_signature_is_kwonly_body_and_token():
    """``post_webhook`` requires keyword-only body_text + idempotency_token.

    The boundary test pins that the injected-client method does
    NOT receive a webhook URL parameter (per locked operator
    decision Q1).
    """
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "DiscordWebhookClientProtocol"
        ):
            for item in node.body:
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == "post_webhook"
                ):
                    found = True
                    args = item.args
                    positional = [a.arg for a in args.args]
                    kwonly = [a.arg for a in args.kwonlyargs]
                    assert positional == ["self"], (
                        f"post_webhook positional args: {positional!r}"
                    )
                    assert set(kwonly) == {
                        "body_text",
                        "idempotency_token",
                    }, f"post_webhook kwonly args: {kwonly!r}"
                    # No webhook_url / url / secret / fingerprint in
                    # any parameter slot.
                    all_arg_names = set(positional) | set(kwonly)
                    for forbidden in (
                        "webhook_url",
                        "url",
                        "secret",
                        "fingerprint",
                        "api_key",
                    ):
                        assert forbidden not in all_arg_names, (
                            "post_webhook must not accept parameter "
                            f"{forbidden!r}"
                        )
    assert found, "DiscordWebhookClientProtocol.post_webhook not found"


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


def test_error_hierarchy_is_module_local_not_stage21_error():
    from PHX2.stage21.errors import Stage21Error

    assert issubclass(DiscordTransportError, Exception)
    assert not issubclass(DiscordTransportError, Stage21Error)
    assert issubclass(DiscordTransportClientError, DiscordTransportError)


# ---------------------------------------------------------------------------
# Live-test marker boundary (no stage21_live marker introduced)
# ---------------------------------------------------------------------------


def _file_registers_live_marker(path: Path) -> bool:
    """Return True iff ``path`` registers a ``stage21_live`` pytest marker.

    The check is AST-based, not substring-based: a docstring or
    comment that mentions ``stage21_live`` to NEGATE its use
    (e.g. "no stage21_live marker is used") must not trip the
    boundary check. The scan looks only for:

      * ``pytest.mark.stage21_live`` attribute access;
      * ``pytestmark = pytest.mark.stage21_live`` or any sequence
        containing it;
      * decorator references whose terminal attribute is
        ``stage21_live`` (e.g.
        ``@pytest.mark.stage21_live`` /
        ``@pytest.mark.stage21_live(reason=...)``).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "stage21_live":
            return True
    return False


def test_no_live_marker_in_production_source():
    """Production source must not register a ``stage21_live`` marker."""
    assert not _file_registers_live_marker(DISCORD_PRIVATE_TRANSPORT_PATH), (
        "Stage 21.3C must not introduce a 'stage21_live' marker; "
        "Stage 21.4 owns the first live send."
    )


def test_no_live_marker_in_offline_tests():
    """Offline tests must not use ``@pytest.mark.stage21_live`` either."""
    offline_test_path = (
        TESTS_STAGE21_ROOT / "test_discord_private_transport_offline.py"
    )
    assert not _file_registers_live_marker(offline_test_path), (
        "Stage 21.3C offline test must not use a 'stage21_live' marker"
    )


def test_no_live_marker_in_21_3c_boundary_test_itself():
    """This boundary file itself must not register a stage21_live marker."""
    assert not _file_registers_live_marker(Path(__file__)), (
        "boundary test must not register a 'stage21_live' marker"
    )


# ---------------------------------------------------------------------------
# No webhook URL leaks via repr / TransportResult / public surface
# ---------------------------------------------------------------------------


def test_transport_source_does_not_materialize_webhook_url_attribute():
    """No top-level / class-level ``webhook_url`` attribute binding.

    The transport stores only ``_webhook_ref`` (a SecretRef). A
    drift that introduces an attribute literally named
    ``webhook_url`` (or ``self.webhook_url = ...``) would expose
    the raw URL inside the transport -- forbidden by Q1.
    """
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr != "webhook_url", (
                "transport must not access a .webhook_url attribute "
                "anywhere -- raw URL must live only inside the injected "
                "client"
            )
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assert target.id != "webhook_url", (
                        "transport must not bind a webhook_url variable"
                    )
                    assert target.id != "WEBHOOK_URL", (
                        "transport must not bind a WEBHOOK_URL constant"
                    )


# ---------------------------------------------------------------------------
# TransportPayload / TransportResult are the only call-surface types
# ---------------------------------------------------------------------------


def test_transport_send_returns_transport_result_type_annotation():
    """The ``send`` method's return annotation is ``TransportResult``."""
    source = _read_source(DISCORD_PRIVATE_TRANSPORT_PATH)
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "DiscordPrivateTransport":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "send":
                    found = True
                    returns = item.returns
                    assert returns is not None, (
                        "send must declare a return annotation"
                    )
                    assert isinstance(returns, ast.Name), (
                        f"send return annotation should be a Name, got "
                        f"{type(returns).__name__}"
                    )
                    assert returns.id == "TransportResult", (
                        f"send returns {returns.id!r}, expected "
                        "'TransportResult'"
                    )
    assert found
