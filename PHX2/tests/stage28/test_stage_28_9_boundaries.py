"""Stage 28.9 boundary scan.

Pins:

  * Every Stage 28.9 production .py file exists at the locked
    path.
  * Every Stage 28.9 operator doc exists at the locked path.
  * Every Stage 28.9 test file exists at the locked path.
  * Stage 28.9 production .py modules other than the bridge
    adapter import only stdlib + Stage 28 sibling modules.
  * The Stage 28.9 bridge adapter (``live_provider_session_adapter.py``)
    is the ONE Stage 28.9 module allowed to import the approved
    Stage 21 / Stage 27 surfaces; the other Stage 28.9
    production modules must NOT import Stage 21-27 production
    code.
  * Stage 28.9 production .py modules never read ``os.environ`` /
    ``os.getenv`` / ``os.environb``.
  * Stage 28.9 production .py modules contain no top-level Call
    (no implicit I/O at import time) and no top-level filesystem
    write call.
  * Stage 28.9 production source carries no URL host literal, no
    raw-secret literal, no auth-header / bearer / API-key prefix
    literal.
  * Stage 28.9 production identifiers never implement a Stage
    29+ enforcement surface, a public router, a subscriber
    router, a paid tier, Telegram, X / social, automated trading,
    wallet / private-key / signer logic, position sizing, trade
    execution, dashboard / control server, or a daemon /
    watchdog / autorestart service.
  * The Stage 28.9 manifest declares the locked basename
    inventories and scope locks.
  * Stage 28.9 production .py modules never import asyncio /
    threading / multiprocessing / subprocess / queue / sched /
    socket / urllib / http.client / ssl, never call sleep /
    wait / schedule / create_task / run_until_complete.
  * No Stage 29 implementation tree exists.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
REPO_ROOT: Path = PHX2_ROOT.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE28_ROOT: Path = PHX2_ROOT / "tests" / "stage28"


# ---------------------------------------------------------------------------
# Locked Stage 28.9 inventories
# ---------------------------------------------------------------------------


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


# The Stage 28.9 bridge adapter is the ONE Stage 28.9 module
# allowed to import approved Stage 21 / Stage 27 surfaces. Every
# other Stage 28.9 production module must NOT.
_STAGE_28_9_BRIDGE_BASENAME: str = "live_provider_session_adapter.py"


# Stage 21 / Stage 27 imports the Stage 28.9 bridge adapter is
# allowed to use. Other Stage 28.9 modules must not import any
# of these (or any other Stage 21-27 module).
_BRIDGE_ALLOWED_STAGE_21_IMPORTS: frozenset[str] = frozenset({
    "PHX2.stage21.normalized_events",
})
_BRIDGE_ALLOWED_STAGE_27_IMPORTS: frozenset[str] = frozenset({
    "PHX2.stage27.live_candidate_assembler",
    "PHX2.stage27.live_dedupe",
    "PHX2.stage27.provider_event_adapter",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_stage28_9_production_py_files() -> list[Path]:
    return [
        STAGE28_ROOT / name
        for name in _STAGE_28_9_PRODUCTION_PY_BASENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Production / doc / test inventory + existence
# ---------------------------------------------------------------------------


def test_every_stage_28_9_production_py_file_exists():
    for name in _STAGE_28_9_PRODUCTION_PY_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.9 requires production .py file {path}"
        )


def test_every_stage_28_9_doc_file_exists():
    for name in _STAGE_28_9_DOC_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.9 requires operator doc {path}"
        )


def test_every_stage_28_9_test_file_exists():
    for name in _STAGE_28_9_TEST_BASENAMES:
        path = TESTS_STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.9 requires test file {path}"
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


def test_no_stage_28_9_production_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage28_9_production_py_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 28.9 production must not read os.environ / "
        f"os.getenv / os.environb; offenders: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    "helius",
    "jupiter",
    "birdeye",
    "discord",
    "discord.",
    "discord_py",
    "telegram",
    "telethon",
    "webhook_client",
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
    "sched",
    "http.client",
    "http",
    "ssl",
)


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
    "PHX2.stage25",
    "PHX2.stage26",
)


def test_no_stage_28_9_production_imports_runtime_module_patterns():
    for path in _iter_stage28_9_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            # Allowed PHX2 modules are exempt from the substring
            # pattern scan -- otherwise the canonical Stage 28
            # module names containing fragments like ``http`` /
            # ``ssl`` would trip the scan. We narrow the
            # exemption to imports that start with ``PHX2.``.
            if target.startswith("PHX2."):
                continue
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
                )


def test_no_stage_28_9_production_imports_prior_stage_18_through_26():
    for path in _iter_stage28_9_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import "
                    f"{target!r}"
                )


def test_only_bridge_adapter_imports_stage_21_or_27():
    """Stage 28.9 admits Stage 21 / Stage 27 imports ONLY in the
    bridge adapter module. The Stage 28.9 models / transport /
    manifest modules MUST NOT import Stage 21 / Stage 27
    production code.
    """
    for path in _iter_stage28_9_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        if path.name == _STAGE_28_9_BRIDGE_BASENAME:
            continue
        for target in targets:
            assert not target.startswith("PHX2.stage21"), (
                f"{path}: only the Stage 28.9 bridge adapter "
                f"may import Stage 21 modules; saw {target!r}"
            )
            assert not target.startswith("PHX2.stage27"), (
                f"{path}: only the Stage 28.9 bridge adapter "
                f"may import Stage 27 modules; saw {target!r}"
            )


def test_bridge_adapter_stage_21_imports_only_approved_modules():
    bridge_path = STAGE28_ROOT / _STAGE_28_9_BRIDGE_BASENAME
    targets = _collect_imported_module_paths(_read(bridge_path))
    stage_21_imports = {
        t for t in targets if t.startswith("PHX2.stage21")
    }
    for target in stage_21_imports:
        assert target in _BRIDGE_ALLOWED_STAGE_21_IMPORTS, (
            f"Stage 28.9 bridge adapter imports unapproved "
            f"Stage 21 module {target!r}; allowed: "
            f"{sorted(_BRIDGE_ALLOWED_STAGE_21_IMPORTS)!r}"
        )


def test_bridge_adapter_stage_27_imports_only_approved_modules():
    bridge_path = STAGE28_ROOT / _STAGE_28_9_BRIDGE_BASENAME
    targets = _collect_imported_module_paths(_read(bridge_path))
    stage_27_imports = {
        t for t in targets if t.startswith("PHX2.stage27")
    }
    for target in stage_27_imports:
        assert target in _BRIDGE_ALLOWED_STAGE_27_IMPORTS, (
            f"Stage 28.9 bridge adapter imports unapproved "
            f"Stage 27 module {target!r}; allowed: "
            f"{sorted(_BRIDGE_ALLOWED_STAGE_27_IMPORTS)!r}"
        )


def test_no_stage_28_9_production_imports_stage_29():
    for path in _iter_stage28_9_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert not target.startswith("PHX2.stage29"), (
                f"{path}: Stage 28.9 must not import Stage 29 "
                f"module; saw {target!r}"
            )


def test_no_stage29_implementation_tree_exists():
    assert not STAGE29_ROOT.exists(), (
        f"Stage 28.9 must not create PHX2/stage29/; saw "
        f"{STAGE29_ROOT}"
    )


def test_no_stage29_tests_tree_exists():
    tests_stage29 = PHX2_ROOT / "tests" / "stage29"
    assert not tests_stage29.exists(), (
        f"Stage 28.9 must not create PHX2/tests/stage29/; saw "
        f"{tests_stage29}"
    )


# ---------------------------------------------------------------------------
# URL host / raw-secret literal scan (excluding the bridge adapter
# which legitimately mentions Stage 21 / Stage 27 module names in
# docstrings but still must not contain URL host or raw-secret
# literals).
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


def test_no_url_host_literal_in_stage_28_9_production_source():
    for path in _iter_stage28_9_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOST_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL host literal {needle!r}"
            )


_FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "x-a" + "pi-key",
    "X-A" + "pi-Key",
    "s" + "k-",
    "p" + "k-",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
)


def test_no_raw_secret_literal_in_stage_28_9_production_source():
    for path in _iter_stage28_9_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES:
            assert needle not in source, (
                f"{path}: forbidden raw-secret-looking literal "
                f"{needle!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden enforcement / public-routing / trading / wallet / daemon
# identifier scan
# ---------------------------------------------------------------------------


_FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS: tuple[str, ...] = (
    # Public / subscriber / paid routing.
    "public" + "_router",
    "subscriber" + "_router",
    "paid" + "_tier_router",
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


def test_no_stage_28_9_production_identifier_implements_later_or_public_surface():
    for path in _iter_stage28_9_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden later-substage or public-"
                    f"routing substring {needle!r}"
                )


# ---------------------------------------------------------------------------
# Stage 21-26 production trees not touched
# ---------------------------------------------------------------------------


def test_no_prior_stage_production_tree_carries_stage_28_9_basename():
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
            if entry.name in _STAGE_28_9_PRODUCTION_PY_BASENAMES:
                leaked.append(f"{stage_dir_name}/{entry.name}")
            if entry.name in _STAGE_28_9_DOC_BASENAMES:
                leaked.append(f"{stage_dir_name}/{entry.name}")
    assert not leaked, (
        f"Stage 28.9 basename leaked into a prior stage tree: "
        f"{leaked!r}"
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


def test_no_stage_28_9_production_has_top_level_call():
    for path in _iter_stage28_9_production_py_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path}: Stage 28.9 production .py modules must "
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


def test_no_stage_28_9_production_writes_at_module_top_level():
    for path in _iter_stage28_9_production_py_files():
        offenders = _module_calls_top_level_filesystem(
            _read(path)
        )
        assert not offenders, (
            f"{path}: Stage 28.9 production .py must not call "
            f"filesystem write helpers at module top level; "
            f"offenders: {offenders!r}"
        )


# ---------------------------------------------------------------------------
# No sleep / async / scheduling calls
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_CALL_ATTRS: frozenset[str] = frozenset(
    {
        "sleep",
        "wait",
        "spawn",
        "schedule",
        "create_task",
        "run_until_complete",
        "start_thread",
    }
)


def test_no_stage_28_9_production_calls_sleep_or_schedule_helpers():
    for path in _iter_stage28_9_production_py_files():
        tree = ast.parse(_read(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    assert (
                        func.attr
                        not in _FORBIDDEN_RUNTIME_CALL_ATTRS
                    ), (
                        f"{path}: Stage 28.9 production .py "
                        f"must not call .{func.attr}()"
                    )
                elif isinstance(func, ast.Name):
                    assert (
                        func.id
                        not in _FORBIDDEN_RUNTIME_CALL_ATTRS
                    ), (
                        f"{path}: Stage 28.9 production .py "
                        f"must not call {func.id}()"
                    )


# ---------------------------------------------------------------------------
# Stage 28.9 manifest declares the locked basename inventories
# ---------------------------------------------------------------------------


def test_manifest_declares_locked_production_py_basenames():
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_PRODUCTION_PY_BASENAMES,
    )

    assert (
        set(STAGE28_9_PRODUCTION_PY_BASENAMES)
        == set(_STAGE_28_9_PRODUCTION_PY_BASENAMES)
    )


def test_manifest_declares_locked_doc_basenames():
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_DOC_BASENAMES,
    )

    assert (
        set(STAGE28_9_DOC_BASENAMES)
        == set(_STAGE_28_9_DOC_BASENAMES)
    )


def test_manifest_declares_locked_test_basenames():
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_TEST_BASENAMES,
    )

    assert (
        set(STAGE28_9_TEST_BASENAMES)
        == set(_STAGE_28_9_TEST_BASENAMES)
    )


def test_manifest_minor_version_is_28_9():
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_MINOR_VERSION,
    )

    assert STAGE28_9_MINOR_VERSION == "28.9"


def test_manifest_schema_version_is_locked():
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_SCHEMA_VERSION,
    )

    assert (
        STAGE28_9_SCHEMA_VERSION
        == "stage28_9_live_provider_session_v0"
    )


def test_manifest_scope_locks_pin_stage_29_exclusions():
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_SCOPE_LOCKS,
    )

    required_phrases = {
        "private live provider session adapter scope",
        (
            "narrow Stage 28 boundary exception: Stage 21 / "
            "Stage 27 imports allowed in adapter module only"
        ),
        "fake provider event source + fake transport in tests only",
        "no real provider connection in tests",
        "no real Discord send in tests",
        "no env reads",
        "no public routing",
        "no subscriber routing",
        "no paid tier routing",
        "no X / social",
        "no Telegram",
        "no Stage 29 enforcement",
        "no approval / activation semantics",
        "no automated trading",
        "no wallet / private-key / signer logic",
        "no position sizing",
        "no trade execution",
        "no dashboard / HTTP control server",
        "no daemon / systemd / watchdog / autorestart service",
        "no Stage 28 closure tag movement",
        "no sleep / no scheduling / no backoff execution",
        "explicit caller-supplied output directory",
        (
            "explicit operator authorization required for live "
            "private session"
        ),
        (
            "Stage 29-pending filter-enforcement marker on every "
            "rendered Discord payload"
        ),
        "redaction-safe records",
    }
    assert required_phrases.issubset(set(STAGE28_9_SCOPE_LOCKS))


def test_manifest_session_outcome_values_match_models():
    from PHX2.stage28.live_provider_session_models import (
        SESSION_OUTCOME_VALUES,
    )
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_SESSION_OUTCOME_VALUES,
    )

    assert (
        set(STAGE28_9_SESSION_OUTCOME_VALUES)
        == set(SESSION_OUTCOME_VALUES)
    )


def test_manifest_refusal_reason_values_match_models():
    from PHX2.stage28.live_provider_session_models import (
        REFUSAL_REASON_VALUES,
    )
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_REFUSAL_REASON_VALUES,
    )

    assert (
        set(STAGE28_9_REFUSAL_REASON_VALUES)
        == set(REFUSAL_REASON_VALUES)
    )


def test_manifest_session_mode_values_match_models():
    from PHX2.stage28.live_provider_session_models import (
        SESSION_MODE_VALUES,
    )
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_SESSION_MODE_VALUES,
    )

    assert (
        set(STAGE28_9_SESSION_MODE_VALUES)
        == set(SESSION_MODE_VALUES)
    )


def test_manifest_session_result_field_names_match_models():
    from PHX2.stage28.live_provider_session_models import (
        STAGE28_9_SESSION_RESULT_FIELD_NAMES as _M,
    )
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_SESSION_RESULT_FIELD_NAMES,
    )

    assert STAGE28_9_SESSION_RESULT_FIELD_NAMES == _M


def test_manifest_runner_artifact_basenames_match_adapter():
    from PHX2.stage28.live_provider_session_adapter import (
        STAGE28_9_RUNNER_ARTIFACT_BASENAMES as _A,
    )
    from PHX2.stage28.stage28_9_manifest import (
        STAGE28_9_RUNNER_ARTIFACT_BASENAMES,
    )

    assert (
        tuple(STAGE28_9_RUNNER_ARTIFACT_BASENAMES) == tuple(_A)
    )


def test_manifest_filter_enforcement_marker_matches_models():
    from PHX2.stage28.live_provider_session_models import (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING as _M,
    )
    from PHX2.stage28.stage28_9_manifest import (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    )

    assert (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING == _M
    )


# ---------------------------------------------------------------------------
# Stage 28 root admits the Stage 28.9 surface
# ---------------------------------------------------------------------------


def test_stage28_root_admits_stage_28_9_files():
    """The Stage 28 tree must admit the locked Stage 28.9
    production / doc surface basenames (the absolute "exactly
    this set" admission is updated in
    ``test_stage_28_6_boundaries.py`` and
    ``test_stage_28_7_boundaries.py``; this scan only asserts
    the Stage 28.9 inventory is present)."""
    actual: set[str] = set()
    for entry in STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    for basename in _STAGE_28_9_PRODUCTION_PY_BASENAMES:
        assert basename in actual, (
            f"PHX2/stage28 must contain Stage 28.9 production "
            f"basename {basename!r}"
        )
    for basename in _STAGE_28_9_DOC_BASENAMES:
        assert basename in actual, (
            f"PHX2/stage28 must contain Stage 28.9 doc "
            f"basename {basename!r}"
        )


def test_tests_stage28_root_admits_stage_28_9_tests():
    actual: set[str] = set()
    for entry in TESTS_STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    for basename in _STAGE_28_9_TEST_BASENAMES:
        assert basename in actual, (
            f"PHX2/tests/stage28 must contain Stage 28.9 test "
            f"basename {basename!r}"
        )
