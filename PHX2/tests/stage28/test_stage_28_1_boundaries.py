"""Stage 28.1 boundary scan.

Pins:

  * Every Stage 28.1 production .py file exists at the locked path.
  * ``PHX2/stage28/`` admits exactly the Stage 28.0 scaffold + the
    Stage 28.1 production surface; no Stage 28.2+ implementation
    file ships at Stage 28.1.
  * ``PHX2/tests/stage28/`` admits exactly the Stage 28.0 spec-lock
    test + the Stage 28.1 test surface; no Stage 28.2+ test file
    ships at Stage 28.1.
  * Stage 28.1 production .py modules never import a network /
    RPC / messaging / Discord / Telegram / X-social / scheduling
    library.
  * Stage 28.1 production .py modules never import Stage 21-27
    production code (the Stage 28.1 wrapper stays standalone --
    it does NOT delegate to Stage 27 readiness directly, it
    introduces its own env-read boundary so the Stage 28 surface
    is decoupled from the Stage 27 closed inventory).
  * Stage 28.1 env-read site is exactly
    ``provider_neutral_readiness.py``; the Stage 28.1 models /
    config / manifest modules never touch ``os.environ`` /
    ``os.getenv`` / ``os.environb``.
  * Stage 28.1 production source carries no URL host literal
    (``discord.com`` / ``api.helius.xyz`` / etc.).
  * Stage 28.1 production identifiers never implement a Stage
    28.2+ surface basename, a public router, a subscriber
    router, a paid tier, Telegram, X / social, Stage 29
    enforcement, automated trading, wallet / private-key /
    signer logic, position sizing, trade execution, dashboard /
    control server, or a daemon / watchdog / autorestart
    service.
  * Stage 28.1 production .py modules contain no top-level Call
    (no implicit I/O at import time).
  * Stage 28.1 production .py modules contain no top-level
    filesystem write call.
  * No Stage 28.2+ implementation basename exists under
    ``PHX2/stage28/`` (dispatch ledger / retry policy / audited
    transport / heartbeat / health snapshot / CLI status /
    longer-session runner / longer-session smoke harness).
  * No Stage 21-27 production tree carries a Stage 28.1
    production basename.
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
# Locked Stage 28.1 inventories
# ---------------------------------------------------------------------------


_STAGE_28_0_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "__init__.py",
    "STAGE_28_0_SPEC_LOCK.md",
)


_STAGE_28_1_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "provider_neutral_models.py",
    "provider_neutral_config.py",
    "provider_neutral_readiness.py",
    "stage28_1_manifest.py",
)


_STAGE_28_1_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_1_provider_neutral_models.py",
    "test_stage_28_1_provider_neutral_config.py",
    "test_stage_28_1_provider_neutral_readiness.py",
    "test_stage_28_1_boundaries.py",
)


_STAGE_28_0_TEST_BASENAMES: tuple[str, ...] = (
    "__init__.py",
    "test_stage_28_0_spec_lock.py",
)


# The Stage 28.1 env-read site -- the ONLY production .py module
# allowed to touch ``os.environ`` / ``os.getenv`` / ``os.environb``.
STAGE28_1_ENV_READ_MODULE: str = "provider_neutral_readiness.py"


# Stage 28.2+ implementation basenames that must remain blocked
# at Stage 28.1.
_STAGE_28_2_PLUS_FORBIDDEN_BASENAMES: tuple[str, ...] = (
    "dispatch_ledger.py",
    "dispatch_ledger_models.py",
    "failure_classification.py",
    "retry_policy.py",
    "audited_http_transport.py",
    "heartbeat_writer.py",
    "health_snapshot_writer.py",
    "cli_status_line.py",
    "bounded_private_session_runner.py",
    "longer_session_smoke_harness.py",
    "stage28_manifest.py",
)


# Forbidden public-routing / enforcement / X-social / Telegram /
# trading / dashboard / daemon basenames that must not appear
# under ``PHX2/stage28/`` at Stage 28.1.
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
# Production-file inventory + existence
# ---------------------------------------------------------------------------


def _iter_stage28_1_production_py_files() -> list[Path]:
    return [
        STAGE28_ROOT / name
        for name in _STAGE_28_1_PRODUCTION_PY_BASENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_stage_28_1_production_py_file_exists():
    for name in _STAGE_28_1_PRODUCTION_PY_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.1 requires production .py file {path}"
        )


def test_every_stage_28_1_test_file_exists():
    for name in _STAGE_28_1_TEST_BASENAMES:
        path = TESTS_STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.1 requires test file {path}"
        )


def test_stage28_root_admits_only_stage_28_0_scaffold_plus_stage_28_1_surface():
    actual: set[str] = set()
    for entry in STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    allowed = set(_STAGE_28_0_PRODUCTION_BASENAMES) | set(
        _STAGE_28_1_PRODUCTION_PY_BASENAMES
    )
    forbidden = actual - allowed
    assert not forbidden, (
        f"PHX2/stage28 admits only Stage 28.0 scaffold + Stage 28.1 "
        f"production surface ({sorted(allowed)!r}); Stage 28.2+ "
        f"files remain blocked. Forbidden entries: "
        f"{sorted(forbidden)!r}"
    )
    missing = allowed - actual
    assert not missing, (
        f"Stage 28.1 inventory missing entries: {sorted(missing)!r}"
    )


def test_tests_stage28_root_admits_only_stage_28_0_plus_stage_28_1_tests():
    actual: set[str] = set()
    for entry in TESTS_STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    allowed = set(_STAGE_28_0_TEST_BASENAMES) | set(
        _STAGE_28_1_TEST_BASENAMES
    )
    forbidden = actual - allowed
    assert not forbidden, (
        f"PHX2/tests/stage28 admits only Stage 28.0 + Stage 28.1 test "
        f"files ({sorted(allowed)!r}); Stage 28.2+ tests remain "
        f"blocked. Forbidden entries: {sorted(forbidden)!r}"
    )


# ---------------------------------------------------------------------------
# Env-read isolation
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


def test_only_provider_neutral_readiness_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage28_1_production_py_files():
        if _module_reads_environ(_read(path)):
            if path.name != STAGE28_1_ENV_READ_MODULE:
                leaked.append(path.name)
    assert not leaked, (
        f"only {STAGE28_1_ENV_READ_MODULE!r} may read os.environ / "
        f"os.getenv / os.environb in Stage 28.1; offenders: "
        f"{leaked!r}"
    )


def test_provider_neutral_readiness_actually_reads_environ():
    """Sanity check: the designated Stage 28.1 env-read boundary
    really does contain the env-read site. If it ever stops, the
    boundary lock has lost its grounding and must be reinstated.
    """
    path = STAGE28_ROOT / STAGE28_1_ENV_READ_MODULE
    assert _module_reads_environ(_read(path)), (
        f"{path}: Stage 28.1 env-read boundary must contain the "
        f"single ``os.environ`` access site"
    )


def test_no_other_stage28_module_reads_environ():
    """Stage 28 env-read isolation must remain
    ``provider_neutral_readiness.py`` only. Stage 28.1 must not
    add a second env-read site anywhere under ``PHX2/stage28/``.
    """
    env_read_modules: list[str] = []
    for entry in STAGE28_ROOT.iterdir():
        if not entry.is_file() or entry.suffix != ".py":
            continue
        if entry.name == STAGE28_1_ENV_READ_MODULE:
            continue
        if _module_reads_environ(_read(entry)):
            env_read_modules.append(entry.name)
    assert not env_read_modules, (
        "Stage 28 env-read boundary must remain isolated to "
        f"{STAGE28_1_ENV_READ_MODULE!r}; offenders: "
        f"{env_read_modules!r}"
    )


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------


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


def test_no_stage_28_1_production_imports_runtime_module_patterns():
    for path in _iter_stage28_1_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern {pattern!r} "
                    f"in import {target!r}"
                )


def test_no_stage_28_1_production_imports_prior_stage_code():
    for path in _iter_stage28_1_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import "
                    f"{target!r}"
                )


# ---------------------------------------------------------------------------
# URL / leak literal scan
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_HOST_SUBSTRINGS: tuple[str, ...] = (
    "discord" + ".com",
    "discordapp" + ".com",
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


def test_no_url_host_literal_in_stage_28_1_production_source():
    for path in _iter_stage28_1_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOST_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL host literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden Stage 28.2+ / public-routing identifier scan
# ---------------------------------------------------------------------------


_FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS: tuple[str, ...] = (
    # Stage 28.2+ implementation surfaces.
    "dispatch" + "_ledger",
    "failure" + "_classification",
    "retry" + "_policy",
    "audited" + "_http_transport",
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
    # Trading verdict language.
    "auto" + "_trade",
    "position" + "_size",
    "trade" + "_executor",
    "wallet" + "_signer",
    "private" + "_key_loader",
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


def test_no_stage_28_1_production_identifier_implements_later_or_public_surface():
    for path in _iter_stage28_1_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in _FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS:
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden later-substage or public-routing "
                    f"substring {needle!r}"
                )


_FORBIDDEN_TRADING_VERDICT_IDENTIFIER_SUBSTRINGS: tuple[str, ...] = (
    "buy_signal",
    "sell_signal",
    "approve_trade",
    "approved_trade",
    "execute_trade",
    "trade_verdict",
    "gate_decision",
    "block_trade",
)


def test_no_stage_28_1_identifier_implements_trading_verdict():
    for path in _iter_stage28_1_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_TRADING_VERDICT_IDENTIFIER_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} carries forbidden "
                    f"trading-verdict substring {needle!r}"
                )


# ---------------------------------------------------------------------------
# Stage 28.2+ basenames must not exist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "basename", _STAGE_28_2_PLUS_FORBIDDEN_BASENAMES
)
def test_no_stage_28_2_plus_basename_under_stage28(basename):
    assert not (STAGE28_ROOT / basename).exists(), (
        f"PHX2/stage28 must not ship Stage 28.2+ implementation "
        f"basename {basename!r} during Stage 28.1"
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


def test_no_prior_stage_production_tree_carries_stage_28_1_basename():
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
            if entry.name in _STAGE_28_1_PRODUCTION_PY_BASENAMES:
                leaked.append(f"{stage_dir_name}/{entry.name}")
    assert not leaked, (
        f"Stage 28.1 production basename leaked into a prior stage "
        f"tree: {leaked!r}"
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


def test_no_stage_28_1_production_has_top_level_call():
    for path in _iter_stage28_1_production_py_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path}: Stage 28.1 production .py modules must "
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


def test_no_stage_28_1_production_writes_at_module_top_level():
    for path in _iter_stage28_1_production_py_files():
        offenders = _module_calls_top_level_filesystem(_read(path))
        assert not offenders, (
            f"{path}: Stage 28.1 production .py must not call "
            f"filesystem write helpers at module top level; "
            f"offenders: {offenders!r}"
        )


# ---------------------------------------------------------------------------
# Stage 28.1 manifest declares the locked basename inventories
# ---------------------------------------------------------------------------


def test_manifest_declares_locked_production_py_basenames():
    from PHX2.stage28.stage28_1_manifest import (
        STAGE28_1_PRODUCTION_PY_BASENAMES,
    )

    assert (
        set(STAGE28_1_PRODUCTION_PY_BASENAMES)
        == set(_STAGE_28_1_PRODUCTION_PY_BASENAMES)
    )


def test_manifest_declares_locked_test_basenames():
    from PHX2.stage28.stage28_1_manifest import (
        STAGE28_1_TEST_BASENAMES,
    )

    assert (
        set(STAGE28_1_TEST_BASENAMES)
        == set(_STAGE_28_1_TEST_BASENAMES)
    )


def test_manifest_scope_locks_pin_stage_28_2_plus_exclusions():
    from PHX2.stage28.stage28_1_manifest import (
        STAGE28_1_SCOPE_LOCKS,
    )

    required_phrases = {
        "no network calls",
        "no Discord dispatch",
        "no dispatch ledger",
        "no retry / backoff",
        "no audited HTTP transport",
        "no heartbeat / health snapshot",
        "no bounded private session runner",
        "no longer-session smoke harness",
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
    assert required_phrases.issubset(set(STAGE28_1_SCOPE_LOCKS))
