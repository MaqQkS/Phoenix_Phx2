"""Stage 27.7b boundary scan.

Pins:

  * Every Stage 27.7b production file exists at the locked path.
  * No Stage 27.7b production .py module reads ``os.environ`` /
    ``os.getenv`` / ``os.environb``. The Stage 27 env-read
    boundary remains exactly ``live_secrets_readiness.py``.
  * No Stage 27.7b production .py module imports a network,
    RPC, messaging, Discord, Telegram, X / social, or scheduling
    library.
  * No Stage 27.7b production .py module imports Stage 21-26
    production code.
  * No Stage 27.7b production .py module imports Stage 27.1
    production code (the env-read / operator-config surface stays
    independent of the sender layer).
  * No Stage 27.7b production source carries a URL host literal,
    a Discord webhook literal, or a raw secret canary.
  * No Stage 27.7b production identifier implements a public
    router / subscriber router / paid tier router / Telegram /
    X-social / enforcement / automated-trading surface.
  * No Stage 27.7b production identifier carries BUY / SELL /
    APPROVED / GATE / BLOCK / EXECUTE / POSITION-SIZE / AUTO-TRADE
    / ENFORCEMENT trading-verdict language.
  * Stage 27.7b production .py modules contain no top-level Call
    (no implicit I/O at import time).
  * Stage 27.7b production .py modules never call
    ``datetime.now`` / ``time.time`` etc. directly.
  * Stage 27.7b production .py modules write to disk only via
    injected helpers (no top-level writer call).
  * No public routing / subscriber / paid tier / Telegram /
    X-social / enforcement / automated trading basename exists
    under ``PHX2/stage27/``.
  * No Stage 25 / Stage 26 production tree carries a Stage 27.7b
    production basename.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"
TESTS_STAGE27_ROOT: Path = PHX2_ROOT / "tests" / "stage27"


_STAGE_27_7B_PRODUCTION_PY_FILENAMES: tuple[str, ...] = (
    "private_discord_models.py",
    "private_discord_sender.py",
    "live_smoke_dispatch.py",
    "stage27_7b_manifest.py",
)


def _iter_stage27_7b_production_py_files() -> list[Path]:
    return [
        STAGE27_ROOT / name
        for name in _STAGE_27_7B_PRODUCTION_PY_FILENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Production-file existence
# ---------------------------------------------------------------------------


def test_every_stage_27_7b_production_py_file_exists():
    for name in _STAGE_27_7B_PRODUCTION_PY_FILENAMES:
        path = STAGE27_ROOT / name
        assert path.is_file(), (
            f"Stage 27.7b requires production .py file {path}"
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


def test_no_stage_27_7b_production_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage27_7b_production_py_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 27.7b production .py modules must not read "
        f"os.environ; offenders: {leaked!r}"
    )


def test_stage_27_env_read_boundary_remains_live_secrets_readiness_only():
    """Stage 27 must isolate every env-read site in
    ``live_secrets_readiness.py``. Stage 27.7b must not add a
    second env-read site anywhere under ``PHX2/stage27/``.
    """
    env_read_modules: list[str] = []
    for entry in STAGE27_ROOT.iterdir():
        if not entry.is_file() or entry.suffix != ".py":
            continue
        if entry.name == "live_secrets_readiness.py":
            continue
        if _module_reads_environ(_read(entry)):
            env_read_modules.append(entry.name)
    assert not env_read_modules, (
        "Stage 27 env-read boundary must remain isolated to "
        "live_secrets_readiness.py; offenders: "
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
)


_FORBIDDEN_STAGE_27_1_MODULE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage27.live_config_errors",
    "PHX2.stage27.live_config_models",
    "PHX2.stage27.live_run_identity",
    "PHX2.stage27.live_secrets_readiness",
    "PHX2.stage27.live_operator_config",
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


def test_no_stage_27_7b_production_imports_runtime_module_patterns():
    for path in _iter_stage27_7b_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
                )


def test_no_stage_27_7b_production_imports_prior_stage_code():
    for path in _iter_stage27_7b_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import "
                    f"{target!r}"
                )


def test_no_stage_27_7b_production_imports_stage_27_1_modules():
    for path in _iter_stage27_7b_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in (
                _FORBIDDEN_STAGE_27_1_MODULE_PREFIXES
            ):
                assert target != forbidden, (
                    f"{path}: Stage 27.7b must not import Stage "
                    f"27.1 module {target!r}"
                )
                assert not target.startswith(forbidden + "."), (
                    f"{path}: Stage 27.7b must not import from "
                    f"Stage 27.1 module {target!r}"
                )


# ---------------------------------------------------------------------------
# URL / leak literal scan (production .py only)
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "public-api.birdeye" + ".so",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
)


def test_no_url_literal_in_stage_27_7b_production_source():
    for path in _iter_stage27_7b_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden later-substage identifier scan
# ---------------------------------------------------------------------------


_FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS: tuple[str, ...] = (
    # Public + subscriber + paid routing.
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
    # Trading verdict language.
    "auto" + "_trade",
    "position" + "_size",
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
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
    return idents


def test_no_stage_27_7b_production_identifier_implements_later_substage():
    for path in _iter_stage27_7b_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in _FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS:
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden later-substage substring "
                    f"{needle!r}"
                )


# ---------------------------------------------------------------------------
# Trading-verdict identifier scan
# ---------------------------------------------------------------------------


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


def test_no_stage_27_7b_identifier_implements_trading_verdict():
    for path in _iter_stage27_7b_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_TRADING_VERDICT_IDENTIFIER_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} carries "
                    f"forbidden trading-verdict substring "
                    f"{needle!r}"
                )


# ---------------------------------------------------------------------------
# Public-routing / enforcement / social basenames must not exist
# ---------------------------------------------------------------------------


_FORBIDDEN_PUBLIC_ROUTING_BASENAMES: tuple[str, ...] = (
    "public_router.py",
    "subscriber_router.py",
    "paid_tier_router.py",
    "live_router.py",
    "telegram_sender.py",
    "telegram_client.py",
    "x_social.py",
    "social_sidecar.py",
    "tweet_ranking.py",
    "enforcement_gate.py",
    "enforcement.py",
    "enforce_policy.py",
    "auto_trade.py",
    "position_sizer.py",
    "discord_bot.py",
    "slash_commands.py",
    "subscriber_models.py",
    "subscriber_db.py",
    "discord.py",
    "telegram.py",
)


@pytest.mark.parametrize(
    "basename", _FORBIDDEN_PUBLIC_ROUTING_BASENAMES
)
def test_no_public_or_enforcement_basename_under_stage27(basename):
    path = STAGE27_ROOT / basename
    assert not path.exists(), (
        f"Stage 27.7b must not introduce public-routing / "
        f"enforcement / social basename {basename!r} under "
        f"PHX2/stage27/; got {path}"
    )


# ---------------------------------------------------------------------------
# Stage 25 / Stage 26 production trees not touched
# ---------------------------------------------------------------------------


def test_no_stage25_or_stage26_production_files_carry_stage27_7b_basename():
    stage25_root = PHX2_ROOT / "stage25"
    stage26_root = PHX2_ROOT / "stage26"
    leaked: list[str] = []
    for root in (stage25_root, stage26_root):
        if not root.exists():
            continue
        for entry in root.iterdir():
            if not entry.is_file():
                continue
            if entry.name in _STAGE_27_7B_PRODUCTION_PY_FILENAMES:
                leaked.append(f"{root.name}/{entry.name}")
    assert not leaked, (
        f"Stage 27.7b production basename leaked into a prior "
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


def test_no_stage_27_7b_production_has_top_level_call():
    for path in _iter_stage27_7b_production_py_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path}: Stage 27.7b production .py modules must "
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
                if (
                    func.attr
                    in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                ):
                    offenders.append(func.attr)
            elif isinstance(func, ast.Name):
                if (
                    func.id
                    in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                ):
                    offenders.append(func.id)
    return offenders


def test_no_stage_27_7b_production_writes_at_import_time():
    for path in _iter_stage27_7b_production_py_files():
        offenders = _module_calls_top_level_filesystem(
            _read(path)
        )
        assert not offenders, (
            f"{path}: Stage 27.7b production .py modules must "
            f"not call filesystem write helpers at import time; "
            f"offenders: {offenders!r}"
        )


# ---------------------------------------------------------------------------
# No direct clock calls
# ---------------------------------------------------------------------------


def _module_calls_direct_clock(source: str) -> list[str]:
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                attr = func.attr
                value = func.value
                if isinstance(value, ast.Name):
                    name = value.id
                    if name == "datetime" and attr == "now":
                        offenders.append("datetime.now")
                    if name == "datetime" and attr == "utcnow":
                        offenders.append("datetime.utcnow")
                    if name == "time" and attr in (
                        "time",
                        "monotonic",
                        "monotonic_ns",
                        "perf_counter",
                    ):
                        offenders.append(f"time.{attr}")
    return offenders


def test_no_stage_27_7b_production_calls_datetime_now():
    for path in _iter_stage27_7b_production_py_files():
        offenders = _module_calls_direct_clock(_read(path))
        assert not offenders, (
            f"{path}: Stage 27.7b must NOT call wall-clock "
            f"helpers directly (use the injected "
            f"Stage27_7bDispatchClock Protocol); offenders: "
            f"{offenders!r}"
        )


# ---------------------------------------------------------------------------
# Stage 27.7b manifest pin
# ---------------------------------------------------------------------------


def test_stage27_7b_manifest_lists_production_py_basenames():
    from PHX2.stage27.stage27_7b_manifest import (
        STAGE27_7B_PRODUCTION_PY_BASENAMES,
    )

    assert set(STAGE27_7B_PRODUCTION_PY_BASENAMES) == set(
        _STAGE_27_7B_PRODUCTION_PY_FILENAMES
    )


def test_stage27_7b_manifest_lists_test_basenames():
    from PHX2.stage27.stage27_7b_manifest import (
        STAGE27_7B_TEST_BASENAMES,
    )

    assert set(STAGE27_7B_TEST_BASENAMES) >= {
        "test_stage_27_7b_private_discord_models.py",
        "test_stage_27_7b_private_discord_sender.py",
        "test_stage_27_7b_live_smoke_dispatch.py",
        "test_stage_27_7b_boundaries.py",
    }


def test_stage27_7b_manifest_handles_minor_version():
    from PHX2.stage27 import stage27_7b_manifest as mfst

    assert mfst.STAGE27_7B_MINOR_VERSION == "27.7b"
    assert mfst.STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION == (
        "stage27_v0_private_discord_dispatch_result"
    )
    assert mfst.STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH == 1


# ---------------------------------------------------------------------------
# Stage 27.7b test inventory present
# ---------------------------------------------------------------------------


_STAGE_27_7B_TEST_FILENAMES: tuple[str, ...] = (
    "test_stage_27_7b_private_discord_models.py",
    "test_stage_27_7b_private_discord_sender.py",
    "test_stage_27_7b_live_smoke_dispatch.py",
    "test_stage_27_7b_boundaries.py",
)


def test_every_stage_27_7b_test_file_exists():
    for name in _STAGE_27_7B_TEST_FILENAMES:
        path = TESTS_STAGE27_ROOT / name
        assert path.is_file(), (
            f"Stage 27.7b requires test file {path}"
        )


# ---------------------------------------------------------------------------
# Stage 27.0 through 27.7b directory allowlist
# ---------------------------------------------------------------------------


_STAGE_27_0_THROUGH_27_7B_LOCKED_PY_MODULES: frozenset[str] = (
    frozenset(
        {
            # Stage 27.0 scaffold.
            "__init__.py",
            # Stage 27.1.
            "live_config_errors.py",
            "live_config_models.py",
            "live_run_identity.py",
            "live_secrets_readiness.py",
            "live_operator_config.py",
            # Stage 27.2.
            "pair_detection_constants.py",
            "pair_detection_models.py",
            "pair_detection_contracts.py",
            "pump_pair_classifier.py",
            # Stage 27.3.
            "provider_ingest_models.py",
            "provider_ingest_contracts.py",
            "provider_event_adapter.py",
            "live_provider_composition.py",
            "stage27_3_manifest.py",
            # Stage 27.4.
            "price_ath_context_models.py",
            "price_ath_context_contracts.py",
            "price_ath_context_reader.py",
            "migration_context_models.py",
            "live_measurement_context.py",
            "stage27_4_manifest.py",
            # Stage 27.5.
            "private_ping_models.py",
            "private_ping_renderer.py",
            "private_ping_provenance.py",
            "private_ping_artifact_writer.py",
            "stage27_5_manifest.py",
            # Stage 27.6.
            "live_dedupe.py",
            "live_candidate_assembler.py",
            "bounded_tradeable_ping_runner.py",
            "stage27_6_manifest.py",
            # Stage 27.7a.
            "dry_run_smoke_harness.py",
            "stage27_7_manifest.py",
            # Stage 27.7b (new).
            "private_discord_models.py",
            "private_discord_sender.py",
            "live_smoke_dispatch.py",
            "stage27_7b_manifest.py",
        }
    )
)


_STAGE_27_0_THROUGH_27_7B_LOCKED_ENTRIES: frozenset[str] = (
    _STAGE_27_0_THROUGH_27_7B_LOCKED_PY_MODULES
    | frozenset(
        {
            "STAGE_27_0_SPEC_LOCK.md",
            "STAGE_27_OPERATOR_RUNBOOK.md",
            "STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md",
            "STAGE_27_CLOSURE_AUDIT.md",
            "STAGE_28_HANDOFF.md",
        }
    )
)


def test_stage27_root_admits_only_locked_27_0_through_27_7b_entries():
    actual: set[str] = set()
    for entry in STAGE27_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = (
        actual - _STAGE_27_0_THROUGH_27_7B_LOCKED_ENTRIES
    )
    assert not forbidden, (
        "PHX2/stage27 admits only the Stage 27.0 through 27.7b "
        f"file set; forbidden entries: {sorted(forbidden)!r}"
    )


def test_stage27_root_py_modules_match_locked_27_7b_set():
    py_files = {
        p.name
        for p in STAGE27_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    unexpected = (
        py_files - _STAGE_27_0_THROUGH_27_7B_LOCKED_PY_MODULES
    )
    assert not unexpected, (
        f"Stage 27.7b must ship only the locked production .py "
        f"set; unexpected: {sorted(unexpected)!r}"
    )
