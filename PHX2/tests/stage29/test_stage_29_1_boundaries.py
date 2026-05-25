"""Stage 29.1 boundary scan.

Pins:

  * Every Stage 29.1 production .py / doc / test / vendored
    file exists at the locked path.
  * Stage 29.1 production .py modules other than the probe /
    extractor / hint-aware-decoder modules must NOT import the
    generated Yellowstone protobuf stubs.
  * Stage 29.1 production .py modules other than the probe
    module must NOT import ``grpc`` / ``grpcio``.
  * NO Stage 29.1 production .py module reads ``os.environ`` /
    ``os.getenv`` / ``os.environb``. The unchanged Stage 28.11
    readiness boundary remains the single env-read site for
    the Stage 28.11 + Stage 29.1 chain.
  * Stage 29.1 production .py modules must NOT import any
    Stage 21-27 module.
  * Stage 29.1 production .py modules must NOT import the
    Stage 28.4 audited transport, Stage 28.6 bounded runner,
    Stage 28.9 adapter / transport / models, or any other
    Stage 28.0 - 28.9 dispatch surface beyond the Stage 28.10
    payload models + the Stage 28.11 readiness / decoder /
    runtime-config + Stage 28.11 grpc generated stubs that
    Stage 29.1 is allowed to wrap.
  * Stage 29.1 production .py modules must NOT import any
    forbidden runtime library (Discord / Telegram / X /
    wallet / trade / SQL / dotenv / keyring / etc.).
  * Stage 29.1 production source carries NO ``Phoenix_Bot``
    path string, NO ``phx1`` substring (case-insensitive), and
    NO Pump.fun bonding-curve program id literal
    (``6EF8rrec...``). PHX1 was design evidence only; Stage
    29.1 is independently re-implemented.
  * Stage 29.1 production source carries NO URL host literal
    and NO raw-secret-looking literal.
  * Stage 29.1 production identifiers never implement a Stage
    29.2 / 29.3 surface, a Pump.fun bonding-curve decoder, a
    public router, a subscriber router, a paid tier, a
    Telegram / X / social sender, an automated trading / wallet
    / private-key / signer surface, a Stage 26 enforcement
    gate, or a daemon / watchdog / autorestart service.
  * Stage 29.1 production modules contain NO top-level Call
    (no implicit I/O at import time) AND NO top-level
    filesystem / subprocess write.
  * The Stage 29.1 manifest pins the same inventories the
    boundary scan asserts.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"
PROTO_STAGE29_1_ROOT: Path = (
    PHX2_ROOT / "proto" / "stage29_1"
)
PROTO_STAGE29_1_SOURCE_ROOT: Path = (
    PROTO_STAGE29_1_ROOT / "source"
)


_STAGE_29_1_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "pumpswap_program_constants.py",
    "pumpswap_hint_models.py",
    "pumpswap_hint_extractor.py",
    "pumpswap_hint_aware_decoder.py",
    "stage29_1_hint_probe_models.py",
    "stage29_1_pumpswap_hint_probe.py",
    "stage29_1_manifest.py",
)


_STAGE_29_1_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_1_PUMPSWAP_HINT_EXTRACTOR_RUNBOOK.md",
)


_STAGE_29_1_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_1_pumpswap_program_constants.py",
    "test_stage_29_1_pumpswap_hint_models.py",
    "test_stage_29_1_pumpswap_hint_extractor.py",
    "test_stage_29_1_pumpswap_hint_aware_decoder.py",
    "test_stage_29_1_hint_probe_models.py",
    "test_stage_29_1_pumpswap_hint_probe.py",
    "test_stage_29_1_runbook.py",
    "test_stage_29_1_boundaries.py",
    "test_stage_29_1_vendored_idl.py",
)


_STAGE_29_1_VENDORED_IDL_BASENAMES: tuple[str, ...] = (
    "pump_amm.json",
)


# Stage 29.1 admits ``grpc`` ONLY in this module.
_STAGE_29_1_GRPC_ADMITTED_BASENAMES: tuple[str, ...] = (
    "stage29_1_pumpswap_hint_probe.py",
)


# Stage 29.1 admits generated Yellowstone protobuf stubs ONLY
# in these modules.
_STAGE_29_1_GENERATED_STUB_ADMITTED_BASENAMES: tuple[
    str, ...
] = (
    "pumpswap_hint_extractor.py",
    "pumpswap_hint_aware_decoder.py",
    "stage29_1_pumpswap_hint_probe.py",
)


# Stage 28.11 generated-stub package prefix.
_STAGE_28_11_GENERATED_PREFIX: str = (
    "PHX2.proto.stage28_11._generated"
)


# Stage 28 imports Stage 29.1 is allowed to use. These are
# upstream-only (Stage 29.1 reuses + wraps Stage 28.10 payload
# models + Stage 28.11 readiness / decoder / runtime-config).
_STAGE_28_ALLOWED_SIBLING_PREFIXES: tuple[str, ...] = (
    "PHX2.stage28.chainstack_yellowstone_models",
    "PHX2.stage28.chainstack_yellowstone_grpc_models",
    "PHX2.stage28.chainstack_yellowstone_grpc_readiness",
    "PHX2.stage28.chainstack_yellowstone_grpc_decode",
)


def _iter_stage29_1_production_py_files() -> list[Path]:
    return [
        STAGE29_ROOT / name
        for name in _STAGE_29_1_PRODUCTION_PY_BASENAMES
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
# 1. Inventory existence
# ---------------------------------------------------------------------------


def test_every_stage_29_1_production_py_file_exists():
    for name in _STAGE_29_1_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.1 requires production .py file {path}"
        )


def test_every_stage_29_1_doc_file_exists():
    for name in _STAGE_29_1_DOC_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.1 requires operator doc {path}"
        )


def test_every_stage_29_1_test_file_exists():
    for name in _STAGE_29_1_TEST_BASENAMES:
        path = TESTS_STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.1 requires test file {path}"
        )


def test_vendored_idl_dir_contains_pinned_files():
    assert PROTO_STAGE29_1_SOURCE_ROOT.is_dir(), (
        f"Stage 29.1 requires {PROTO_STAGE29_1_SOURCE_ROOT}"
    )
    actual = {
        p.name
        for p in PROTO_STAGE29_1_SOURCE_ROOT.iterdir()
        if p.is_file()
    }
    expected = set(_STAGE_29_1_VENDORED_IDL_BASENAMES)
    assert actual == expected, (
        f"Stage 29.1 vendored IDL set drift: expected="
        f"{sorted(expected)!r} actual={sorted(actual)!r}"
    )


def test_proto_parent_dir_is_pep420_namespace_no_init():
    """``PHX2/proto/`` remains a PEP 420 namespace package.
    Re-introducing ``PHX2/proto/__init__.py`` would require
    Stage 28.11 + Stage 29.1 boundary admission updates.
    """
    init_path = PHX2_ROOT / "proto" / "__init__.py"
    assert not init_path.exists(), (
        f"PHX2/proto/ must remain a PEP 420 namespace package; "
        f"the {init_path!s} file is not authorized."
    )


# ---------------------------------------------------------------------------
# 2. Env-read isolation
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


def test_zero_stage_29_1_production_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage29_1_production_py_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 29.1 production must NOT read os.environ. "
        f"The unchanged Stage 28.11 readiness module remains "
        f"the single env-read site. Offenders: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# 3. grpc / generated-stub admission
# ---------------------------------------------------------------------------


_GRPC_IMPORT_PATTERNS: tuple[str, ...] = (
    "grpc",
    "grpcio",
    "grpc_tools",
)


_GENERATED_STUB_IMPORT_PATTERNS: tuple[str, ...] = (
    _STAGE_28_11_GENERATED_PREFIX,
)


def _module_imports_any(
    source: str, needles: tuple[str, ...],
) -> set[str]:
    targets = _collect_imported_module_paths(source)
    hits: set[str] = set()
    for t in targets:
        for n in needles:
            if t == n or t.startswith(n + "."):
                hits.add(t)
    return hits


def test_only_probe_imports_grpc():
    for path in _iter_stage29_1_production_py_files():
        hits = _module_imports_any(
            _read(path), _GRPC_IMPORT_PATTERNS,
        )
        if path.name in _STAGE_29_1_GRPC_ADMITTED_BASENAMES:
            continue
        assert not hits, (
            f"{path.name}: Stage 29.1 admits grpc imports only "
            f"in {_STAGE_29_1_GRPC_ADMITTED_BASENAMES!r}; "
            f"offenders: {sorted(hits)!r}"
        )


def test_only_admitted_modules_import_generated_stubs():
    for path in _iter_stage29_1_production_py_files():
        hits = _module_imports_any(
            _read(path), _GENERATED_STUB_IMPORT_PATTERNS,
        )
        if (
            path.name
            in _STAGE_29_1_GENERATED_STUB_ADMITTED_BASENAMES
        ):
            continue
        assert not hits, (
            f"{path.name}: Stage 29.1 admits generated stub "
            f"imports only in "
            f"{_STAGE_29_1_GENERATED_STUB_ADMITTED_BASENAMES!r}; "
            f"offenders: {sorted(hits)!r}"
        )


def test_probe_module_imports_grpc_and_generated_stubs():
    src = _read(
        STAGE29_ROOT / "stage29_1_pumpswap_hint_probe.py",
    )
    assert "import grpc" in src
    assert _STAGE_28_11_GENERATED_PREFIX in src


# ---------------------------------------------------------------------------
# 4. Forbidden prior-stage / Stage 28.9 dispatch surface imports
# ---------------------------------------------------------------------------


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


def test_no_stage_29_1_production_imports_prior_stages():
    for path in _iter_stage29_1_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden prior-stage "
                    f"import {target!r}"
                )


_FORBIDDEN_STAGE_28_DISPATCH_IMPORTS: tuple[str, ...] = (
    "PHX2.stage28.live_provider_session_adapter",
    "PHX2.stage28.live_provider_session_transport",
    "PHX2.stage28.live_provider_session_models",
    "PHX2.stage28.bounded_private_session_runner",
    "PHX2.stage28.audited_http_transport",
    "PHX2.stage28.dispatch_ledger",
    "PHX2.stage28.heartbeat_writer",
    "PHX2.stage28.health_snapshot_writer",
    "PHX2.stage28.failure_classification",
    "PHX2.stage28.retry_policy",
    "PHX2.stage28.chainstack_yellowstone_event_source",
    "PHX2.stage28.chainstack_yellowstone_candidate_assembler",
    "PHX2.stage28.chainstack_yellowstone_contracts",
    "PHX2.stage28.chainstack_yellowstone_grpc_client",
    "PHX2.stage28.chainstack_yellowstone_grpc_probe",
)


def test_no_stage_29_1_production_imports_dispatch_surface():
    for path in _iter_stage29_1_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert target not in (
                _FORBIDDEN_STAGE_28_DISPATCH_IMPORTS
            ), (
                f"{path.name}: Stage 29.1 must not import "
                f"Stage 28 dispatch / event-source surface "
                f"{target!r}"
            )


# ---------------------------------------------------------------------------
# 5. Forbidden runtime libraries
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "urllib3",
    "websockets",
    "solders",
    "solana",
    "construct",
    "base58",
    "helius",
    "jupiter",
    "birdeye",
    "discord",
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
)


def test_no_stage_29_1_production_imports_forbidden_runtime():
    for path in _iter_stage29_1_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if target.startswith("PHX2."):
                continue
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path.name}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
                )


# ---------------------------------------------------------------------------
# 6. PHX1 import path / Pump.fun bonding-curve program id
# ---------------------------------------------------------------------------


def test_no_stage_29_1_production_imports_phx1():
    for path in _iter_stage29_1_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            assert "phoenix_bot" not in lower, (
                f"{path.name}: forbidden PHX1 import path "
                f"{target!r}"
            )
            assert "phx1" not in lower, (
                f"{path.name}: forbidden PHX1 substring in "
                f"import path {target!r}"
            )


def test_no_stage_29_1_production_source_carries_phx1_path():
    for path in _iter_stage29_1_production_py_files():
        source = _read(path)
        lower = source.lower()
        assert "phoenix_bot" not in lower, (
            f"{path.name}: forbidden 'Phoenix_Bot' substring"
        )


def test_no_stage_29_1_production_carries_pump_fun_program_id():
    # Pump.fun bonding-curve program id ``6EF8rrec...`` is
    # deferred; it must not appear anywhere in Stage 29.1
    # production source.
    for path in _iter_stage29_1_production_py_files():
        source = _read(path)
        assert (
            "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
            not in source
        ), (
            f"{path.name}: forbidden Pump.fun bonding-curve "
            f"program id literal"
        )


# ---------------------------------------------------------------------------
# 7. URL host / raw-secret literal scan
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_HOSTS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "public-api.birdeye" + ".so",
    "birdeye" + ".so",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com",
    "yellowstone" + ".chainstack",
)


def test_no_url_host_literal_in_stage_29_1_production_source():
    for path in _iter_stage29_1_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOSTS:
            assert needle not in source, (
                f"{path.name}: forbidden URL host literal "
                f"{needle!r}"
            )


_FORBIDDEN_RAW_SECRET_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "BIRDEYE_API" + "_KEY=",
    "CHAINSTACK_API" + "_KEY=",
)


def test_no_raw_secret_literal_in_stage_29_1_production_source():
    for path in _iter_stage29_1_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
            assert needle not in source, (
                f"{path.name}: forbidden raw-secret-looking "
                f"literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. Forbidden later-substage / public-routing identifier scan
# ---------------------------------------------------------------------------


_FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS: tuple[
    str, ...
] = (
    "public" + "_router",
    "subscriber" + "_router",
    "paid" + "_tier_router",
    "telegram" + "_sender",
    "telegram" + "_client",
    "x" + "_social",
    "social" + "_sidecar",
    "tweet" + "_ranking",
    "enforcement" + "_gate",
    "enforce" + "_policy",
    "approval" + "_gate",
    "approval" + "_status",
    "enforcement" + "_result",
    "auto" + "_trade",
    "position" + "_size",
    "trade" + "_executor",
    "wallet" + "_signer",
    "private" + "_key_loader",
    "buy" + "_signal",
    "sell" + "_signal",
    "execute" + "_trade",
    "control" + "_server",
    "http" + "_control_server",
    "auto" + "restart",
    "systemd" + "_unit",
    "birdeye" + "_price",
    "birdeye" + "_ath",
    "birdeye" + "_readiness",
    "dexscreener" + "_dispatch",
    "helius" + "_price",
    "tradeable" + "_smoke_harness",
    "bonding" + "_curve_decoder",
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


def test_no_stage_29_1_production_identifier_implements_forbidden_surface():
    for path in _iter_stage29_1_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{path.name}: forbidden later-substage / "
                    f"public-routing identifier substring "
                    f"{needle!r} in identifier {ident!r}"
                )


# ---------------------------------------------------------------------------
# 9. No top-level Call / no top-level filesystem or subprocess
# ---------------------------------------------------------------------------


def _has_top_level_call(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            return True
    return False


def test_no_stage_29_1_production_has_top_level_call():
    for path in _iter_stage29_1_production_py_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path.name}: Stage 29.1 production must not "
            f"contain top-level Call (no implicit I/O at "
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
        "system",
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
    }
)


def test_no_stage_29_1_production_has_top_level_write():
    for path in _iter_stage29_1_production_py_files():
        tree = ast.parse(_read(path))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(
                node.value, ast.Call,
            ):
                func = node.value.func
                if isinstance(func, ast.Attribute):
                    assert (
                        func.attr
                        not in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                    ), (
                        f"{path.name}: forbidden top-level "
                        f"write/io call {func.attr!r}"
                    )
                elif isinstance(func, ast.Name):
                    assert (
                        func.id
                        not in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                    ), (
                        f"{path.name}: forbidden top-level "
                        f"write/io call {func.id!r}"
                    )


# ---------------------------------------------------------------------------
# 10. Stage 29.1 manifest pins
# ---------------------------------------------------------------------------


def test_manifest_pins_production_inventory():
    from PHX2.stage29.stage29_1_manifest import (
        STAGE29_1_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_1_PRODUCTION_PY_BASENAMES
        == _STAGE_29_1_PRODUCTION_PY_BASENAMES
    )


def test_manifest_pins_doc_inventory():
    from PHX2.stage29.stage29_1_manifest import (
        STAGE29_1_DOC_BASENAMES,
    )
    assert (
        STAGE29_1_DOC_BASENAMES == _STAGE_29_1_DOC_BASENAMES
    )


def test_manifest_pins_test_inventory():
    from PHX2.stage29.stage29_1_manifest import (
        STAGE29_1_TEST_BASENAMES,
    )
    assert (
        STAGE29_1_TEST_BASENAMES == _STAGE_29_1_TEST_BASENAMES
    )


def test_manifest_pins_grpc_and_stub_admission():
    from PHX2.stage29.stage29_1_manifest import (
        STAGE29_1_GENERATED_STUB_ADMITTED_BASENAMES,
        STAGE29_1_GRPC_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_1_GRPC_ADMITTED_BASENAMES
        == _STAGE_29_1_GRPC_ADMITTED_BASENAMES
    )
    assert (
        STAGE29_1_GENERATED_STUB_ADMITTED_BASENAMES
        == _STAGE_29_1_GENERATED_STUB_ADMITTED_BASENAMES
    )


def test_manifest_pins_zero_env_read_admission():
    from PHX2.stage29.stage29_1_manifest import (
        STAGE29_1_ENV_READ_ADMITTED_BASENAMES,
    )
    assert STAGE29_1_ENV_READ_ADMITTED_BASENAMES == ()


def test_manifest_lists_forbidden_surfaces():
    from PHX2.stage29.stage29_1_manifest import (
        STAGE29_1_FORBIDDEN_SURFACES,
    )
    expected = {
        "Discord send",
        "diagnostic Discord smoke",
        "Birdeye adapter",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / private-key / signer logic",
        "Stage 26 policy enforcement activation",
        "Stage 29.2 Birdeye adapter implementation",
        "Stage 29.3 tradeable Discord smoke",
        "Pump.fun bonding-curve decoder",
        "Pump.fun bonding-curve program id constant",
        "PHX1 import path",
    }
    assert expected.issubset(set(STAGE29_1_FORBIDDEN_SURFACES))


# ---------------------------------------------------------------------------
# 11. Upstream sibling import sanity
# ---------------------------------------------------------------------------


def test_stage_29_1_production_only_imports_authorized_stage_28():
    """Every PHX2.stage28.* import in Stage 29.1 production must
    target an authorized sibling prefix; non-authorized
    sibling imports are forbidden.
    """
    for path in _iter_stage29_1_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if not target.startswith("PHX2.stage28"):
                continue
            ok = any(
                target == prefix or target.startswith(prefix + ".")
                for prefix in _STAGE_28_ALLOWED_SIBLING_PREFIXES
            )
            assert ok, (
                f"{path.name}: stage28 import {target!r} is "
                f"not in the Stage 29.1 authorized sibling "
                f"prefix list {_STAGE_28_ALLOWED_SIBLING_PREFIXES!r}"
            )
