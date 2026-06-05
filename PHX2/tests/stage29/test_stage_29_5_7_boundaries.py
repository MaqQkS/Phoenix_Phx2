"""Stage 29.5.7 boundary scan.

Pins that the Stage 29.5.7 production slice is a pure, offline producer: zero env
reads, zero outbound network, no third-party base58 / base64 / datetime / time /
Stage 30 / Stage 21-28 / Stage 29.3-29.4 imports (the 8-byte create_pool
discriminator is recovered by a hand-rolled, stdlib-only base58 reader -- no
imported decoder), no module-body Call except ``@dataclass``, no PHX1 /
Pump.fun-bonding-curve / URL-host / raw-secret literal -- and that the committed
Stage 30.11.8 confirmation was NOT loosened.
"""

from __future__ import annotations

import ast
from pathlib import Path


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"


_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_7_helius_raw_migration_models.py",
    "stage29_5_7_helius_raw_migration_normalizer.py",
    "stage29_5_7_live_migration_evidence_producer.py",
    "stage29_5_7_manifest.py",
)


_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_7_HELIUS_RAW_MIGRATION_RUNBOOK.md",
)


_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_7_helius_raw_migration_models.py",
    "test_stage_29_5_7_helius_raw_migration_normalizer.py",
    "test_stage_29_5_7_live_migration_evidence_producer.py",
    "test_stage_29_5_7_composition.py",
    "test_stage_29_5_7_vendored_idl.py",
    "test_stage_29_5_7_boundaries.py",
    "test_stage_29_5_7_manifest.py",
    "test_stage_29_5_7_fake_evidence_proof.py",
)


# Stage 29.5.7 production may import ONLY these external PHX2 modules (plus stdlib
# + sibling stage29_5_7_* modules): the Stage 29.5 migration-models record + the
# Stage 29.1 PumpSwap program constants (the authoritative, vendored-IDL-pinned
# program id + quote mints).
_ADMITTED_EXTERNAL_PHX2_IMPORTS: frozenset[str] = frozenset(
    {
        "PHX2.stage29.stage29_5_migration_models",
        "PHX2.stage29.pumpswap_program_constants",
    }
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _iter_production_files() -> list[Path]:
    return [STAGE29_ROOT / name for name in _PRODUCTION_PY_BASENAMES]


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


def test_every_production_py_file_exists() -> None:
    for name in _PRODUCTION_PY_BASENAMES:
        assert (STAGE29_ROOT / name).is_file(), name


def test_doc_exists() -> None:
    for name in _DOC_BASENAMES:
        assert (STAGE29_ROOT / name).is_file(), name


def test_every_test_file_exists() -> None:
    for name in _TEST_BASENAMES:
        assert (TESTS_STAGE29_ROOT / name).is_file(), name


# ---------------------------------------------------------------------------
# 2. Env-read isolation
# ---------------------------------------------------------------------------


_ENV_ATTR_NAMES: frozenset[str] = frozenset({"environ", "getenv", "environb"})


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


def test_no_production_reads_environ() -> None:
    for path in _iter_production_files():
        assert not _module_reads_environ(_read(path)), path.name


# ---------------------------------------------------------------------------
# 3. Outbound-network + forbidden-runtime isolation (incl. base58/base64/datetime)
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "websocket",
    "http.client",
    "socket",
    "grpc",
    "asyncio",
    "solders",
    "solana",
    "construct",
    "base58",
    "base64",
    "helius",
    "discord",
    "telegram",
    "telethon",
    "apscheduler",
    "celery",
    "sqlalchemy",
    "sqlite3",
    "dotenv",
    "keyring",
    "threading",
    "multiprocessing",
    "subprocess",
)


def test_no_production_imports_forbidden_runtime() -> None:
    for path in _iter_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if target.startswith("PHX2."):
                continue
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path.name}: forbidden runtime import {target!r}"
                )


def test_no_production_imports_datetime_or_time() -> None:
    # The anchor formatter is pure integer arithmetic; no wall-clock source is
    # imported anywhere in the slice.
    for path in _iter_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert target != "time", f"{path.name} imports time"
            assert target != "datetime", f"{path.name} imports datetime"
            assert not target.startswith("datetime."), path.name


# ---------------------------------------------------------------------------
# 4. No forbidden prior-stage / Stage 28 / Stage 30 / Stage 29.3-29.4 imports
# ---------------------------------------------------------------------------


_FORBIDDEN_STAGE_PREFIXES: tuple[str, ...] = (
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
    "PHX2.stage28",
    "PHX2.stage30",
    "PHX2.stage31",
)


def test_no_production_imports_forbidden_stages() -> None:
    for path in _iter_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden import {target!r}"
                )
            assert not target.startswith("PHX2.stage29.stage29_3_"), (
                f"{path.name}: must not import Stage 29.3 {target!r}"
            )
            assert not target.startswith("PHX2.stage29.stage29_4_"), (
                f"{path.name}: must not import Stage 29.4 {target!r}"
            )


def test_production_imports_zero_stage_30_modules() -> None:
    # The reverse-import boundary: Stage 30 mirrors Stage 29 BY VALUE; Stage 29.5.7
    # must NOT import any Stage 30 module.
    for path in _iter_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert not target.startswith("PHX2.stage30"), (
                f"{path.name}: Stage 29.5.7 must not import Stage 30 {target!r}"
            )


def test_production_only_imports_admitted_external_phx2() -> None:
    for path in _iter_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if not target.startswith("PHX2."):
                continue
            if target.startswith("PHX2.stage29.stage29_5_7_"):
                continue
            assert target in _ADMITTED_EXTERNAL_PHX2_IMPORTS, (
                f"{path.name}: PHX2 import {target!r} not admitted"
            )


# ---------------------------------------------------------------------------
# 5. PHX1 / Pump.fun / URL host / raw secret scan
# ---------------------------------------------------------------------------


def test_no_production_source_carries_phx1_path() -> None:
    needles = ("phoenix" + "_bot", "p" + "hx1", "phoenix-" + "1")
    for path in _iter_production_files():
        lower = _read(path).lower()
        for needle in needles:
            assert needle not in lower, f"{path.name}: {needle!r}"


def test_no_production_carries_pump_fun_bonding_curve_program_id() -> None:
    pump_program = "6EF8rrec" + "thR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    for path in _iter_production_files():
        assert pump_program not in _read(path), path.name


_FORBIDDEN_URL_HOSTS: tuple[str, ...] = (
    "discord" + ".com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + "-rpc.com",
    "birdeye" + ".so",
    "chainstack" + ".com",
    "dexscreener" + ".com",
    "t" + ".me/",
)


def test_no_url_host_literal_in_production_source() -> None:
    for path in _iter_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOSTS:
            assert needle not in source, f"{path.name}: {needle!r}"


_FORBIDDEN_RAW_SECRET_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "HELIUS_API" + "_KEY=",
    "HELIUS_WS" + "_URL=",
    "DISCORD_WEBHOOK" + "_URL=",
)


def test_no_raw_secret_literal_in_production_source() -> None:
    for path in _iter_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
            assert needle not in source, f"{path.name}: {needle!r}"


# ---------------------------------------------------------------------------
# 6. No module-body Call (no implicit I/O at import time) except @dataclass
# ---------------------------------------------------------------------------


def _is_allowed_dataclass_decorator_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name) and func.id == "dataclass":
        return True
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "dataclasses"
        and func.attr == "dataclass"
    ):
        return True
    return False


def _module_body_forbidden_calls(source: str) -> list[str]:
    tree = ast.parse(source)
    forbidden: list[str] = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Function bodies run only when called; only signature-level Calls
            # would execute at import. Mirror the Stage 29.5.6 scan: inspect
            # decorators / defaults / annotations.
            scopes: list = list(stmt.decorator_list)
            scopes += list(stmt.args.defaults)
            scopes += [d for d in stmt.args.kw_defaults if d is not None]
            for node in scopes:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        forbidden.append(f"{stmt.name}:{ast.dump(sub.func)}")
        elif isinstance(stmt, ast.ClassDef):
            for d in stmt.decorator_list:
                if isinstance(d, ast.Call) and _is_allowed_dataclass_decorator_call(d):
                    continue
                for sub in ast.walk(d):
                    if isinstance(sub, ast.Call):
                        forbidden.append(f"{stmt.name}@decorator")
        else:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call):
                    forbidden.append(f"{type(stmt).__name__}:{ast.dump(sub.func)}")
    return forbidden


def test_no_module_body_calls_except_dataclass() -> None:
    for path in _iter_production_files():
        forbidden = _module_body_forbidden_calls(_read(path))
        assert not forbidden, f"{path.name}: module-body Calls {forbidden!r}"


# ---------------------------------------------------------------------------
# 7. The committed Stage 30.11.8 confirmation was NOT modified / loosened
# ---------------------------------------------------------------------------


def test_stage_30_11_8_confirmation_not_loosened() -> None:
    adapter_src = _read(
        STAGE30_ROOT / "stage30_11_8_migration_confirmation_adapter.py"
    )
    # The three confirmation guards must remain present byte-for-byte: the on-chain
    # COMPLETE gate, the stale-warning gate, and the strict UTC-Z-only anchor
    # pattern (Z\Z, never the +00:00 offset form).
    assert "STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE" in adapter_src
    assert "_stale_in_warnings" in adapter_src
    assert "_is_valid_iso8601_utc" in adapter_src
    assert r"Z\Z" in adapter_src

    from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
        STAGE30_11_8_CONFIRMING_MEASUREMENT_STATUS,
        STAGE30_11_8_REDACTION_STATUS_SAFE,
    )

    assert STAGE30_11_8_CONFIRMING_MEASUREMENT_STATUS == "COMPLETE"
    assert STAGE30_11_8_REDACTION_STATUS_SAFE == "SAFE"


def test_stage_29_5_7_does_not_appear_in_stage_30_11_8_imports() -> None:
    # The committed Stage 30.11.8 adapter must not import Stage 29.5.7 (it stays a
    # leaf; the source plugs in at the injected seam).
    adapter_src = _read(
        STAGE30_ROOT / "stage30_11_8_migration_confirmation_adapter.py"
    )
    assert "stage29_5_7" not in adapter_src
