"""Stage 28.3b boundary scan.

Pins:

  * Every Stage 28.3b production .py file exists at the locked
    path.
  * Every Stage 28.3b test file exists at the locked path.
  * Stage 28.3b production .py modules never import a network /
    RPC / messaging / Discord / Telegram / X-social / scheduling /
    threading / asyncio / subprocess / queue library.
  * Stage 28.3b production .py modules never import Stage 21-27
    production code, never import Stage 28.1 production code,
    never import Stage 28.2 production code (the retry policy
    consumes Stage 28.3a classification records and nothing
    else).
  * Stage 28.3b production .py modules never read ``os.environ`` /
    ``os.getenv`` / ``os.environb``. Every policy input is a
    caller-supplied Stage 28.3a classification + closed-set
    counters.
  * Stage 28.3b production .py modules contain no top-level Call
    (no implicit I/O at import time) and no top-level filesystem
    write call.
  * Stage 28.3b production source carries no URL host literal
    (``discord`` ``.com`` / ``api.helius`` ``.xyz`` / etc.), no
    URL scheme literal, and no raw-secret literal.
  * Stage 28.3b production identifiers never implement a Stage
    28.4+ surface basename, a public router, a subscriber router,
    a paid tier, Telegram, X / social, Stage 29 enforcement,
    automated trading, wallet / private-key / signer logic,
    position sizing, trade execution, dashboard / control server,
    or a daemon / watchdog / autorestart service.
  * Stage 28.4+ implementation basenames remain blocked at Stage
    28.3b (audited_http_transport / heartbeat_writer /
    health_snapshot_writer / cli_status_line /
    bounded_private_session_runner / longer_session_smoke_harness /
    Stage 28-wide manifest).
  * No public-routing / enforcement / X-social / Telegram /
    trading / dashboard / daemon basename appears under
    ``PHX2/stage28/`` at Stage 28.3b.
  * No Stage 21-27 production tree carries a Stage 28.3b
    production basename.
  * The Stage 28.3b manifest declares the locked basename
    inventories and scope locks.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent
PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
TESTS_STAGE28_ROOT: Path = PHX2_ROOT / "tests" / "stage28"


# ---------------------------------------------------------------------------
# Locked Stage 28.3b inventories
# ---------------------------------------------------------------------------


_STAGE_28_3B_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "retry_policy_models.py",
    "retry_policy.py",
    "stage28_3b_manifest.py",
)


_STAGE_28_3B_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_3b_retry_policy_models.py",
    "test_stage_28_3b_retry_policy.py",
    "test_stage_28_3b_boundaries.py",
)


# Stage 28.8+ implementation basenames that remain blocked at
# Stage 28.7. (Stage 28.3b amendment moved ``retry_policy.py``
# and ``retry_policy_models.py`` off the previously-forbidden
# list. Stage 28.4 amendment moved ``audited_http_transport.py``
# and ``audited_http_transport_models.py`` off this list. Stage
# 28.5 amendment moved ``heartbeat_writer.py``,
# ``health_snapshot_writer.py``, ``cli_status_line.py``,
# ``health_status_models.py``, and ``stage28_5_manifest.py`` off
# this list. Stage 28.6 amendment moved
# ``session_runner_models.py``,
# ``bounded_private_session_runner.py``, and
# ``stage28_6_manifest.py`` off this list. Stage 28.7 amendment
# moved ``longer_session_smoke_harness.py`` and
# ``stage28_7_manifest.py`` off this list. Each per-substage
# manifest filename is intentionally not blocked because that is
# a per-substage manifest filename, not the future Stage 28-wide
# closure manifest.)
_STAGE_28_4_PLUS_FORBIDDEN_BASENAMES: tuple[str, ...] = (
    "stage29_manifest.py",
    "STAGE_29_CLOSURE_AUDIT.md",
    "STAGE_30_HANDOFF.md",
)


# Forbidden public-routing / enforcement / X-social / Telegram /
# trading / dashboard / daemon basenames that must not appear
# under ``PHX2/stage28/`` at Stage 28.3b.
_FORBIDDEN_PUBLIC_ROUTING_OR_ENFORCEMENT_BASENAMES: tuple[str, ...] = (
    "public_router.py",
    "subscriber_router.py",
    "paid_tier_router.py",
    "live_router.py",
    "telegram_sender.py",
    "telegram_client.py",
    "x_social.py",
    "social_sidecar.py",
    "tweet_ranking.py",
    "social_scoring.py",
    "enforcement_gate.py",
    "enforcement.py",
    "enforce_policy.py",
    "auto_trade.py",
    "position_sizer.py",
    "trade_executor.py",
    "wallet_signer.py",
    "private_key_loader.py",
    "discord_bot.py",
    "slash_commands.py",
    "subscriber_models.py",
    "subscriber_db.py",
    "discord.py",
    "telegram.py",
    "dashboard.py",
    "http_control_server.py",
    "control_server.py",
    "watchdog.py",
    "autorestart.py",
    "daemon.py",
    "systemd_unit.py",
)


# ---------------------------------------------------------------------------
# File iteration helpers
# ---------------------------------------------------------------------------


def _iter_stage28_3b_production_py_files() -> list[Path]:
    return [
        STAGE28_ROOT / name
        for name in _STAGE_28_3B_PRODUCTION_PY_BASENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Production-file inventory + existence
# ---------------------------------------------------------------------------


def test_every_stage_28_3b_production_py_file_exists():
    for name in _STAGE_28_3B_PRODUCTION_PY_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.3b requires production .py file {path}"
        )


def test_every_stage_28_3b_test_file_exists():
    for name in _STAGE_28_3B_TEST_BASENAMES:
        path = TESTS_STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.3b requires test file {path}"
        )


# ---------------------------------------------------------------------------
# Env-read isolation: Stage 28.3b production must NOT read env
# ---------------------------------------------------------------------------


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


def _module_reads_environ(source: str) -> bool:
    tree = ast.parse(source)
    os_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    if alias.name in _ENV_ATTR_NAMES:
                        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in _ENV_ATTR_NAMES
            ):
                return True
    return False


def test_no_stage_28_3b_production_reads_environ():
    """Stage 28.3b policy inputs are caller-supplied Stage 28.3a
    classifications + closed-set counters. The policy has no
    notion of an env-derived input; no Stage 28.3b production
    .py may read ``os.environ`` / ``os.getenv`` / ``os.environb``.
    """
    leaked: list[str] = []
    for path in _iter_stage28_3b_production_py_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 28.3b production must not read os.environ / "
        f"os.getenv / os.environb; offenders: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "urllib.request",
    "websockets",
    "grpc",
    "grpcio",
    "helius",
    "jupiter",
    "birdeye",
    "discord.",
    "discord_py",
    "telegram",
    "telethon",
    "webhook",
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "sqlalchemy",
    "sqlite3",
    "dotenv",
    "keyring",
    "tweepy",
    "twitter",
    "socket",
    "asyncio",
    "threading",
    "multiprocessing",
    "subprocess",
    "queue",
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
    "PHX2.stage25",
    "PHX2.stage26",
    "PHX2.stage27",
)


# Stage 28.1 and Stage 28.2 production modules MUST NOT be imported
# by Stage 28.3b. The retry policy is a Stage 28.3a-consumer layer;
# the provider-neutral config wrapper (28.1) and dispatch ledger
# (28.2) are independent surfaces. Stage 28.2 ledger-state tokens
# flow into the Stage 28.3a classifier as caller-supplied
# closed-set string literals, and Stage 28.3b receives them via
# the classification record only.
_FORBIDDEN_STAGE_28_1_28_2_IMPORTS: tuple[str, ...] = (
    "PHX2.stage28.provider_neutral_models",
    "PHX2.stage28.provider_neutral_config",
    "PHX2.stage28.provider_neutral_readiness",
    "PHX2.stage28.stage28_1_manifest",
    "PHX2.stage28.dispatch_ledger_models",
    "PHX2.stage28.dispatch_ledger",
    "PHX2.stage28.stage28_2_manifest",
)


def _collect_imported_module_paths(source: str) -> set[str]:
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


def test_no_stage_28_3b_production_imports_runtime_module_patterns():
    for path in _iter_stage28_3b_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern {pattern!r} "
                    f"in import {target!r}"
                )


def test_no_stage_28_3b_production_imports_prior_stage_code():
    for path in _iter_stage28_3b_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import "
                    f"{target!r}"
                )


def test_no_stage_28_3b_production_imports_stage_28_1_or_28_2_modules():
    for path in _iter_stage28_3b_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert target not in _FORBIDDEN_STAGE_28_1_28_2_IMPORTS, (
                f"{path}: Stage 28.3b must not import Stage 28.1 / "
                f"Stage 28.2 production module {target!r}"
            )


def test_stage_28_3b_only_imports_stdlib_and_stage_28_3a_or_3b():
    """Stage 28.3b production .py modules may import only:

      * stdlib modules (``typing``, ``math``, ...).
      * Stage 28.3a production modules (the classifier models).
      * Stage 28.3b sibling production modules.
    """
    allowed_stdlib_prefixes: frozenset[str] = frozenset(
        {
            "typing",
            "math",
            "__future__",
            "collections",
            "dataclasses",
            "enum",
            "functools",
            "itertools",
        }
    )
    allowed_stage_28_3a_prefixes: frozenset[str] = frozenset(
        {
            "PHX2.stage28.failure_classification_models",
            "PHX2.stage28.failure_classification",
            "PHX2.stage28.stage28_3a_manifest",
        }
    )
    allowed_stage_28_3b_prefixes: frozenset[str] = frozenset(
        {
            "PHX2.stage28.retry_policy_models",
            "PHX2.stage28.retry_policy",
            "PHX2.stage28.stage28_3b_manifest",
        }
    )
    allowed = (
        allowed_stdlib_prefixes
        | allowed_stage_28_3a_prefixes
        | allowed_stage_28_3b_prefixes
    )
    for path in _iter_stage28_3b_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            head = target.split(".")[0] if "." in target else target
            if head in allowed_stdlib_prefixes:
                continue
            if target in allowed:
                continue
            assert False, (
                f"{path}: Stage 28.3b production .py must import "
                f"only stdlib / Stage 28.3a / Stage 28.3b modules; "
                f"saw {target!r}"
            )


# ---------------------------------------------------------------------------
# URL / leak literal scan
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_HOST_SUBSTRINGS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + ".rpc.com",
    "public-api.birdeye" + ".so",
    "birdeye" + ".so/v1",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com/",
    "yellowstone" + ".chainstack",
)


def test_no_url_host_literal_in_stage_28_3b_production_source():
    for path in _iter_stage28_3b_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOST_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL host literal {needle!r}"
            )


_FORBIDDEN_URL_SCHEME_PATTERNS: tuple[str, ...] = (
    # Concatenated to keep this test file itself out of the
    # boundary scan's URL-leak hit list.
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
)


def test_no_url_scheme_literal_in_stage_28_3b_production_source():
    for path in _iter_stage28_3b_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_SCHEME_PATTERNS:
            assert needle not in source, (
                f"{path}: forbidden URL-scheme literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden Stage 28.4+ / public-routing identifier scan
# ---------------------------------------------------------------------------


_FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS: tuple[str, ...] = (
    # Stage 28.4+ implementation surfaces.
    "audited" + "_http_transport",
    "audited" + "_transport",
    "heartbeat" + "_writer",
    "health" + "_snapshot",
    "cli" + "_status_line",
    "bounded" + "_private_session_runner",
    "longer" + "_session_smoke_harness",
    # Public / subscriber / paid routing.
    "public" + "_router",
    "subscriber" + "_router",
    "paid" + "_tier_router",
    "paid" + "_tier",
    "live" + "_router",
    # Other transports / surfaces.
    "telegram" + "_sender",
    "telegram" + "_client",
    "x" + "_social",
    "social" + "_sidecar",
    "tweet" + "_ranking",
    # Stage 29 enforcement language.
    "enforcement" + "_gate",
    "enforce" + "_policy",
    "approval" + "_gate",
    "approval" + "_status",
    "enforcement" + "_result",
    # Trading verdict language.
    "auto" + "_trade",
    "position" + "_size",
    "trade" + "_executor",
    "wallet" + "_signer",
    "private" + "_key_loader",
    "buy" + "_signal",
    "sell" + "_signal",
    "execute" + "_trade",
    # Dashboards / daemons / watchdogs.
    "control" + "_server",
    "http" + "_control_server",
    "auto" + "restart",
    "systemd" + "_unit",
)


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
    return idents


def test_no_stage_28_3b_production_identifier_implements_later_or_public_surface():
    for path in _iter_stage28_3b_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden later-substage or public-routing "
                    f"substring {needle!r}"
                )


# ---------------------------------------------------------------------------
# Stage 28.4+ basenames must not exist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", _STAGE_28_4_PLUS_FORBIDDEN_BASENAMES
)
def test_no_stage_28_4_plus_basename_under_stage28(basename):
    assert not (STAGE28_ROOT / basename).exists(), (
        f"PHX2/stage28 must not ship Stage 28.7+ implementation "
        f"basename {basename!r} during Stage 28.6"
    )


@pytest.mark.parametrize(
    "basename", _FORBIDDEN_PUBLIC_ROUTING_OR_ENFORCEMENT_BASENAMES
)
def test_no_public_routing_or_enforcement_basename_under_stage28(
    basename,
):
    assert not (STAGE28_ROOT / basename).exists(), (
        f"PHX2/stage28 must not introduce public-routing / "
        f"enforcement / social / trading / dashboard basename "
        f"{basename!r}"
    )


# ---------------------------------------------------------------------------
# Stage 21-27 production trees not touched
# ---------------------------------------------------------------------------


def test_no_prior_stage_production_tree_carries_stage_28_3b_basename():
    leaked: list[str] = []
    for stage_dir_name in (
        "stage21",
        "stage22",
        "stage23",
        "stage24",
        "stage25",
        "stage26",
        "stage27",
    ):
        root = PHX2_ROOT / stage_dir_name
        if not root.exists():
            continue
        for entry in root.iterdir():
            if not entry.is_file():
                continue
            if entry.name in _STAGE_28_3B_PRODUCTION_PY_BASENAMES:
                leaked.append(f"{stage_dir_name}/{entry.name}")
    assert not leaked, (
        f"Stage 28.3b production basename leaked into a prior "
        f"stage tree: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# No top-level Call / no top-level write
# ---------------------------------------------------------------------------


def _has_top_level_call(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            return True
    return False


def test_no_stage_28_3b_production_has_top_level_call():
    for path in _iter_stage28_3b_production_py_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path}: Stage 28.3b production .py modules must "
            f"contain no top-level Call (no implicit I/O at "
            f"import time)"
        )


_FORBIDDEN_TOP_LEVEL_WRITE_TARGETS: frozenset[str] = frozenset(
    {
        "write_bytes",
        "write_text",
        "open",
        "mkdir",
        "touch",
        "unlink",
        "rmdir",
        "rename",
        "replace",
    }
)


def _module_calls_top_level_filesystem(source: str) -> list[str]:
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            func = node.value.func
            if isinstance(func, ast.Attribute):
                if func.attr in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS:
                    offenders.append(func.attr)
            elif isinstance(func, ast.Name):
                if func.id in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS:
                    offenders.append(func.id)
    return offenders


def test_no_stage_28_3b_production_writes_at_module_top_level():
    for path in _iter_stage28_3b_production_py_files():
        offenders = _module_calls_top_level_filesystem(_read(path))
        assert not offenders, (
            f"{path}: Stage 28.3b production .py must not call "
            f"filesystem write helpers at module top level; "
            f"offenders: {offenders!r}"
        )


# ---------------------------------------------------------------------------
# Sleep / async / scheduling rejection at the source-AST level
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_CALL_ATTRS: frozenset[str] = frozenset(
    {
        "sleep",
        "wait",
        "spawn",
        "schedule",
        "create_task",
        "run_until_complete",
    }
)


def test_no_stage_28_3b_production_calls_sleep_or_schedule_helpers():
    """Stage 28.3b is a pure decision layer. It must never call
    ``sleep`` / ``wait`` / ``spawn`` / ``schedule`` /
    ``create_task`` / ``run_until_complete`` -- those are retry
    executor responsibilities and live in a later Stage 28
    substage.
    """
    for path in _iter_stage28_3b_production_py_files():
        tree = ast.parse(_read(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    assert (
                        func.attr
                        not in _FORBIDDEN_RUNTIME_CALL_ATTRS
                    ), (
                        f"{path}: Stage 28.3b production .py must "
                        f"not call .{func.attr}(); that responsibility "
                        f"belongs to a later Stage 28 substage"
                    )
                elif isinstance(func, ast.Name):
                    assert (
                        func.id
                        not in _FORBIDDEN_RUNTIME_CALL_ATTRS
                    ), (
                        f"{path}: Stage 28.3b production .py must "
                        f"not call {func.id}(); that responsibility "
                        f"belongs to a later Stage 28 substage"
                    )


# ---------------------------------------------------------------------------
# Raw-secret literal scan over production source
# ---------------------------------------------------------------------------


_FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES: tuple[str, ...] = (
    # Auth header substrings. Deliberately concatenated so this
    # test file itself is not flagged by a downstream boundary
    # scan; the actual production source must not carry them.
    "B" + "earer ",
    "A" + "uthorization:",
    "x-a" + "pi-key",
    "X-A" + "pi-Key",
    # Common API-key prefixes.
    "s" + "k-",
    "p" + "k-",
    # Webhook env-name leaks.
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
)


def test_no_raw_secret_literal_in_stage_28_3b_production_source():
    for path in _iter_stage28_3b_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES:
            assert needle not in source, (
                f"{path}: forbidden raw-secret-looking literal "
                f"{needle!r}"
            )


# ---------------------------------------------------------------------------
# Stage 28.3b manifest declares the locked basename inventories
# ---------------------------------------------------------------------------


def test_manifest_declares_locked_production_py_basenames():
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_PRODUCTION_PY_BASENAMES,
    )

    assert (
        set(STAGE28_3B_PRODUCTION_PY_BASENAMES)
        == set(_STAGE_28_3B_PRODUCTION_PY_BASENAMES)
    )


def test_manifest_declares_locked_test_basenames():
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_TEST_BASENAMES,
    )

    assert (
        set(STAGE28_3B_TEST_BASENAMES)
        == set(_STAGE_28_3B_TEST_BASENAMES)
    )


def test_manifest_minor_version_is_28_3b():
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_MINOR_VERSION,
    )

    assert STAGE28_3B_MINOR_VERSION == "28.3b"


def test_manifest_schema_version_is_locked():
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_SCHEMA_VERSION,
    )

    assert (
        STAGE28_3B_SCHEMA_VERSION == "stage28_3b_retry_policy_v0"
    )


def test_manifest_scope_locks_pin_stage_28_4_plus_exclusions():
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_SCOPE_LOCKS,
    )

    required_phrases = {
        "retry-policy-only scope",
        "no env reads",
        "no network calls",
        "no HTTP",
        "no gRPC",
        "no Discord dispatch",
        "no provider connection",
        "no retry execution",
        "no sleep / no scheduling / no backoff execution",
        "no audited HTTP transport",
        "no heartbeat / health snapshot",
        "no CLI status line",
        "no bounded private session runner",
        "no longer-session smoke harness",
        "no live smoke",
        "no Stage 29 enforcement",
        "no X / social",
        "no Telegram",
        "no public routing",
        "no subscriber routing",
        "no paid tier routing",
        "no automated trading",
        "no wallet / private-key / signer logic",
        "no position sizing",
        "no trade execution",
        "no dashboard / HTTP control server",
        "no daemon / systemd / watchdog / autorestart service",
    }
    assert required_phrases.issubset(set(STAGE28_3B_SCOPE_LOCKS))


def test_manifest_retry_outcome_values_match_locked_model_values():
    from PHX2.stage28.retry_policy_models import (
        RETRY_OUTCOME_VALUES,
    )
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_RETRY_OUTCOME_VALUES,
    )

    assert (
        set(STAGE28_3B_RETRY_OUTCOME_VALUES)
        == set(RETRY_OUTCOME_VALUES)
    )


def test_manifest_retry_profile_name_values_match_locked_model_values():
    from PHX2.stage28.retry_policy_models import (
        RETRY_PROFILE_NAME_VALUES,
    )
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_RETRY_PROFILE_NAME_VALUES,
    )

    assert (
        set(STAGE28_3B_RETRY_PROFILE_NAME_VALUES)
        == set(RETRY_PROFILE_NAME_VALUES)
    )


def test_manifest_terminal_reason_values_match_locked_model_values():
    from PHX2.stage28.retry_policy_models import (
        TERMINAL_REASON_VALUES,
    )
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_TERMINAL_REASON_VALUES,
    )

    assert (
        set(STAGE28_3B_TERMINAL_REASON_VALUES)
        == set(TERMINAL_REASON_VALUES)
    )


def test_manifest_safe_retry_reason_code_values_match_locked_model_values():
    from PHX2.stage28.retry_policy_models import (
        SAFE_RETRY_REASON_CODE_VALUES,
    )
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_SAFE_RETRY_REASON_CODE_VALUES,
    )

    assert (
        set(STAGE28_3B_SAFE_RETRY_REASON_CODE_VALUES)
        == set(SAFE_RETRY_REASON_CODE_VALUES)
    )


def test_manifest_retry_after_cap_is_locked_at_30():
    from PHX2.stage28.stage28_3b_manifest import (
        STAGE28_3B_RETRY_AFTER_MAX_SECONDS,
    )

    assert STAGE28_3B_RETRY_AFTER_MAX_SECONDS == 30.0


# ---------------------------------------------------------------------------
# Stage 28 root admits exactly the locked surface through Stage 28.4
# ---------------------------------------------------------------------------


# Stage 28.4 narrow amendment (authorized 2026-05-23): the audited
# private Discord HTTP transport substage is authorized and adds
# the production / test inventory below.
_STAGE_28_4_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "audited_http_transport_models.py",
    "audited_http_transport.py",
    "stage28_4_manifest.py",
)


_STAGE_28_4_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_4_audited_http_transport_models.py",
    "test_stage_28_4_audited_http_transport.py",
    "test_stage_28_4_boundaries.py",
)


# Stage 28.5 narrow amendment (authorized 2026-05-23): the
# heartbeat / health-snapshot / CLI-status substage is authorized
# and adds the production / test inventory below.
_STAGE_28_5_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "health_status_models.py",
    "heartbeat_writer.py",
    "health_snapshot_writer.py",
    "cli_status_line.py",
    "stage28_5_manifest.py",
)


_STAGE_28_5_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_5_health_status_models.py",
    "test_stage_28_5_heartbeat_writer.py",
    "test_stage_28_5_health_snapshot_writer.py",
    "test_stage_28_5_cli_status_line.py",
    "test_stage_28_5_boundaries.py",
)


# Stage 28.6 narrow amendment (authorized 2026-05-23): the
# longer-session bounded private runner substage is authorized
# and adds the production / test inventory below.
_STAGE_28_6_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "session_runner_models.py",
    "bounded_private_session_runner.py",
    "stage28_6_manifest.py",
)


_STAGE_28_6_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_6_session_runner_models.py",
    "test_stage_28_6_bounded_private_session_runner.py",
    "test_stage_28_6_boundaries.py",
)


# Stage 28.7 narrow amendment: the longer-session smoke harness +
# controlled live smoke runbook substage is authorized and adds
# the production / doc / test inventory below.
_STAGE_28_7_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "longer_session_smoke_harness.py",
    "stage28_7_manifest.py",
)


_STAGE_28_7_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md",
    "STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md",
)


_STAGE_28_7_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_7_longer_session_smoke_harness.py",
    "test_stage_28_7_boundaries.py",
    "test_stage_28_7_smoke_docs.py",
)


# Stage 28.8 narrow amendment: the closure audit + Stage 29
# handoff + Stage 28-wide manifest substage is authorized and
# adds the production / doc / test inventory below.
_STAGE_28_8_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage28_manifest.py",
)


_STAGE_28_8_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_CLOSURE_AUDIT.md",
    "STAGE_29_HANDOFF.md",
)


_STAGE_28_8_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_8_closure_audit.py",
    "test_stage_28_8_stage29_handoff.py",
    "test_stage_28_8_manifest.py",
    "test_stage_28_8_boundaries.py",
)


# Stage 28.9 narrow amendment: the private live provider session
# adapter substage is a post-Stage-28-closure operational bridge.
_STAGE_28_9_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "live_provider_session_models.py",
    "live_provider_session_adapter.py",
    "live_provider_session_transport.py",
    "stage28_9_manifest.py",
)


_STAGE_28_9_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_9_PRIVATE_LIVE_PROVIDER_RUNBOOK.md",
)


_STAGE_28_9_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_9_live_provider_session_models.py",
    "test_stage_28_9_live_provider_session_adapter.py",
    "test_stage_28_9_live_provider_session_transport.py",
    "test_stage_28_9_runbook.py",
    "test_stage_28_9_boundaries.py",
)


def test_stage28_root_admits_only_28_0_through_28_3b_surface():
    """Sanity: at Stage 28.7 the ``PHX2/stage28`` tree must
    admit exactly the union of the Stage 28.0 scaffold + Stage
    28.1 production surface + Stage 28.2 production surface +
    Stage 28.3a production surface + Stage 28.3b production
    surface + Stage 28.4 production surface + Stage 28.5
    production surface + Stage 28.6 production surface + Stage
    28.7 production / doc surface (plus the interpreter's
    ``__pycache__`` cache, which is build noise).
    """
    actual: set[str] = set()
    for entry in STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    expected = {
        # Stage 28.0 scaffold.
        "__init__.py",
        "STAGE_28_0_SPEC_LOCK.md",
        # Stage 28.1 production .py surface.
        "provider_neutral_models.py",
        "provider_neutral_config.py",
        "provider_neutral_readiness.py",
        "stage28_1_manifest.py",
        # Stage 28.2 production .py surface.
        "dispatch_ledger_models.py",
        "dispatch_ledger.py",
        "stage28_2_manifest.py",
        # Stage 28.3a production .py surface.
        "failure_classification_models.py",
        "failure_classification.py",
        "stage28_3a_manifest.py",
    } | set(_STAGE_28_3B_PRODUCTION_PY_BASENAMES) | set(
        _STAGE_28_4_PRODUCTION_PY_BASENAMES
    ) | set(_STAGE_28_5_PRODUCTION_PY_BASENAMES) | set(
        _STAGE_28_6_PRODUCTION_PY_BASENAMES
    ) | set(_STAGE_28_7_PRODUCTION_PY_BASENAMES) | set(
        _STAGE_28_7_DOC_BASENAMES
    ) | set(_STAGE_28_8_PRODUCTION_PY_BASENAMES) | set(
        _STAGE_28_8_DOC_BASENAMES
    ) | set(_STAGE_28_9_PRODUCTION_PY_BASENAMES) | set(
        _STAGE_28_9_DOC_BASENAMES
    )
    assert actual == expected, (
        f"PHX2/stage28 tree drift: expected={sorted(expected)!r} "
        f"actual={sorted(actual)!r}"
    )


def test_tests_stage28_root_admits_only_28_0_through_28_3b_tests():
    actual: set[str] = set()
    for entry in TESTS_STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    expected = {
        "__init__.py",
        "test_stage_28_0_spec_lock.py",
        # Stage 28.1 test surface.
        "test_stage_28_1_provider_neutral_models.py",
        "test_stage_28_1_provider_neutral_config.py",
        "test_stage_28_1_provider_neutral_readiness.py",
        "test_stage_28_1_boundaries.py",
        # Stage 28.2 test surface.
        "test_stage_28_2_dispatch_ledger_models.py",
        "test_stage_28_2_dispatch_ledger.py",
        "test_stage_28_2_boundaries.py",
        # Stage 28.3a test surface.
        "test_stage_28_3a_failure_classification_models.py",
        "test_stage_28_3a_failure_classification.py",
        "test_stage_28_3a_boundaries.py",
    } | set(_STAGE_28_3B_TEST_BASENAMES) | set(
        _STAGE_28_4_TEST_BASENAMES
    ) | set(_STAGE_28_5_TEST_BASENAMES) | set(
        _STAGE_28_6_TEST_BASENAMES
    ) | set(_STAGE_28_7_TEST_BASENAMES) | set(
        _STAGE_28_8_TEST_BASENAMES
    ) | set(_STAGE_28_9_TEST_BASENAMES)
    assert actual == expected, (
        f"PHX2/tests/stage28 drift: expected={sorted(expected)!r} "
        f"actual={sorted(actual)!r}"
    )
