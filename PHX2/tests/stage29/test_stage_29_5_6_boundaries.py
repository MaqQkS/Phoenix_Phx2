"""Stage 29.5.6 boundary scan.

Pins:

  * Every Stage 29.5.6 production .py / doc / test file exists
    at the locked path.
  * Stage 29.5.6 admits ZERO env-read sites.
  * Stage 29.5.6 admits ZERO outbound HTTP / WS / socket / gRPC
    imports across all production files.
  * Stage 29.5.6 production modules must NOT import any Stage
    21-26 module, any Stage 28 module, any Stage 29.3 / Stage
    29.4 production module, any forbidden runtime library, or
    any PHX1 / legacy phoenix-1 path.
  * Stage 29.5.6 production code may import ONLY:
      - stdlib (``typing``),
      - ``PHX2.stage29.stage29_5_migration_models``,
      - ``PHX2.stage29.stage29_5_5_render_models``,
      - sibling ``PHX2.stage29.stage29_5_6_*`` modules.
  * Stage 29.5.6 production source carries NO PHX1 substring,
    NO Pump.fun bonding-curve program id literal, NO URL host
    literal, NO raw-secret-looking literal.
  * Stage 29.5.6 production modules contain NO top-level Call
    (no implicit I/O at import time). The only admitted
    module-body Call shape is ``@dataclass(...)``.
  * Stage 29.3 production source carries ZERO ``stage29_5*``
    import.
  * Stage 29.4 production source carries ZERO ``stage29_5*``
    import.
  * The locked filter_enforcement_status token
    ``NOT_ACTIVE_STAGE_29_PENDING`` is preserved verbatim.
  * Stage 29.5 / Stage 29.5.2 / Stage 29.5.3 / Stage 29.5.4 /
    Stage 29.5.5 production inventories survive unchanged at
    Stage 29.5.6.
"""

from __future__ import annotations

import ast
from pathlib import Path


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"


_STAGE_29_5_6_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_6_private_ping_migration_context_injector.py",
    "stage29_5_6_manifest.py",
)


_STAGE_29_5_6_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_RUNBOOK.md",
)


_STAGE_29_5_6_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_6_private_ping_migration_context.py",
    "test_stage_29_5_6_boundaries.py",
    "test_stage_29_5_6_manifest.py",
    "test_stage_29_5_6_spec_lock.py",
)


# Admitted PHX2 import allowlist (exact dotted names). The
# injector module imports Stage 29.5 migration models for the
# locked enforcement token + Stage 29.5.5 render models for the
# rendered-block validator helper + class. The manifest module
# imports the sibling injector module + Stage 29.5 migration
# models. Stage 29.5.6 imports NOTHING ELSE in PHX2.
_ADMITTED_EXTERNAL_PHX2_IMPORTS: frozenset[str] = frozenset(
    {
        "PHX2.stage29.stage29_5_migration_models",
        "PHX2.stage29.stage29_5_5_render_models",
    }
)


def _iter_stage29_5_6_production_files() -> list[Path]:
    return [
        STAGE29_ROOT / name
        for name in _STAGE_29_5_6_PRODUCTION_PY_BASENAMES
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


def test_every_stage_29_5_6_production_py_file_exists() -> None:
    for name in _STAGE_29_5_6_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.5.6 requires production .py file {path}"
        )


def test_every_stage_29_5_6_doc_file_exists() -> None:
    for name in _STAGE_29_5_6_DOC_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.5.6 requires doc {path}"
        )


def test_every_stage_29_5_6_test_file_exists() -> None:
    for name in _STAGE_29_5_6_TEST_BASENAMES:
        path = TESTS_STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.5.6 requires test {path}"
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


def test_no_stage_29_5_6_production_reads_environ() -> None:
    leaked: list[str] = []
    for path in _iter_stage29_5_6_production_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 29.5.6 admits ZERO env-read sites; offenders: "
        f"{leaked!r}"
    )


# ---------------------------------------------------------------------------
# 3. Outbound-network isolation
# ---------------------------------------------------------------------------


_OUTBOUND_NETWORK_IMPORT_PATTERNS: tuple[str, ...] = (
    "urllib",
    "urllib.request",
    "urllib.parse",
    "urllib.error",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "websocket",
    "http.client",
    "socket",
    "grpc",
    "asyncio",
)


def _module_imports_any(
    source: str, needles: tuple[str, ...]
) -> set[str]:
    targets = _collect_imported_module_paths(source)
    hits: set[str] = set()
    for t in targets:
        for n in needles:
            if t == n or t.startswith(n + "."):
                hits.add(t)
    return hits


def test_no_stage_29_5_6_production_imports_outbound_network() -> None:
    for path in _iter_stage29_5_6_production_files():
        hits = _module_imports_any(
            _read(path),
            _OUTBOUND_NETWORK_IMPORT_PATTERNS,
        )
        assert not hits, (
            f"{path.name}: Stage 29.5.6 admits ZERO outbound-"
            f"network imports; offenders: {sorted(hits)!r}"
        )


# ---------------------------------------------------------------------------
# 4. No forbidden prior-stage / Stage 28 / Stage 29.x imports
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


def test_no_stage_29_5_6_production_imports_prior_stages() -> None:
    for path in _iter_stage29_5_6_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in (
                _FORBIDDEN_PRIOR_STAGE_PREFIXES
            ):
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden prior-stage "
                    f"import {target!r}"
                )


def test_no_stage_29_5_6_production_imports_stage_28() -> None:
    for path in _iter_stage29_5_6_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert not target.startswith("PHX2.stage28."), (
                f"{path.name}: Stage 29.5.6 must not import "
                f"any Stage 28 module; offender {target!r}"
            )
            assert target != "PHX2.stage28", (
                f"{path.name}: Stage 29.5.6 must not import "
                f"Stage 28 package directly"
            )


def test_no_stage_29_5_6_production_imports_stage_29_3() -> None:
    for path in _iter_stage29_5_6_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert not target.startswith(
                "PHX2.stage29.stage29_3_",
            ), (
                f"{path.name}: Stage 29.5.6 must not import "
                f"any Stage 29.3 production module; the "
                f"injector is consumed BY Stage 29.3 mode-3 "
                f"via its existing parameter slot, not the "
                f"other way around. Offender: {target!r}"
            )


def test_no_stage_29_5_6_production_imports_stage_29_4() -> None:
    forbidden_stage_29_4_modules: tuple[str, ...] = (
        "PHX2.stage29.stage29_4_soak_orchestrator",
        "PHX2.stage29.stage29_4_dedupe_index",
        "PHX2.stage29.stage29_4_soak_artifact_writer",
        "PHX2.stage29.stage29_4_manifest",
        "PHX2.stage29.stage29_4_soak_models",
    )
    for path in _iter_stage29_5_6_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in forbidden_stage_29_4_modules:
                assert target != forbidden, (
                    f"{path.name}: Stage 29.5.6 must not "
                    f"import {forbidden!r}"
                )


def test_stage_29_5_6_production_only_imports_admitted_external_phx2() -> None:
    for path in _iter_stage29_5_6_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if not target.startswith("PHX2."):
                continue
            if target.startswith(
                "PHX2.stage29.stage29_5_6_",
            ):
                continue
            assert target in _ADMITTED_EXTERNAL_PHX2_IMPORTS, (
                f"{path.name}: PHX2 import {target!r} not in "
                f"Stage 29.5.6 admitted-external allowlist "
                f"{sorted(_ADMITTED_EXTERNAL_PHX2_IMPORTS)!r}"
            )


# ---------------------------------------------------------------------------
# 5. Forbidden runtime libraries
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "solders",
    "solana",
    "construct",
    "base58",
    "helius",
    "jupiter",
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
    "threading",
    "multiprocessing",
    "subprocess",
    "queue",
    "sched",
    "dexscreener",
    "signal",
)


def test_no_stage_29_5_6_production_imports_forbidden_runtime() -> None:
    for path in _iter_stage29_5_6_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if target.startswith("PHX2."):
                continue
            lower = target.lower()
            for pattern in (
                _FORBIDDEN_RUNTIME_MODULE_PATTERNS
            ):
                assert pattern not in lower, (
                    f"{path.name}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
                )


# ---------------------------------------------------------------------------
# 6. PHX1 / Pump.fun / URL host / raw-secret scan
# ---------------------------------------------------------------------------


def test_no_stage_29_5_6_production_imports_phx1() -> None:
    for path in _iter_stage29_5_6_production_files():
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


def test_no_stage_29_5_6_production_source_carries_phx1_path() -> None:
    """Scan production source case-insensitively for every legacy
    pre-PHX2 substring (``phoenix_bot`` / ``phx1`` /
    ``phoenix-1``). The forbidden-substring needles are
    concatenated literally so this test file itself does not
    trip the scan over its own pinned vocabulary.
    """
    forbidden_legacy_substrings: tuple[str, ...] = (
        "phoenix" + "_bot",
        "p" + "hx1",
        "phoenix-" + "1",
    )
    for path in _iter_stage29_5_6_production_files():
        source = _read(path)
        lower = source.lower()
        for needle in forbidden_legacy_substrings:
            assert needle not in lower, (
                f"{path.name}: forbidden legacy substring "
                f"{needle!r}"
            )


def test_no_stage_29_5_6_production_carries_pump_fun_program_id() -> None:
    pump_program = (
        "6EF8rrec" + "thR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    )
    for path in _iter_stage29_5_6_production_files():
        source = _read(path)
        assert pump_program not in source, (
            f"{path.name}: forbidden Pump.fun bonding-curve "
            f"program id literal"
        )


_FORBIDDEN_URL_HOSTS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + "-rpc.com",
    "public-api.birdeye" + ".so",
    "pro-api.birdeye" + ".so",
    "business-api.birdeye" + ".so",
    "birdeye" + ".so",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com",
    "yellowstone" + ".chainstack",
    "dexscreener" + ".com",
)


def test_no_url_host_literal_in_stage_29_5_6_production_source() -> None:
    for path in _iter_stage29_5_6_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOSTS:
            assert needle not in source, (
                f"{path.name}: forbidden URL host literal "
                f"{needle!r}"
            )


_FORBIDDEN_RAW_SECRET_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_WS" + "_URL=",
    "HELIUS_WS" + "_ENDPOINT=",
    "BIRDEYE_API" + "_KEY=",
    "CHAINSTACK_API" + "_KEY=",
)


def test_no_raw_secret_literal_in_stage_29_5_6_production_source() -> None:
    for path in _iter_stage29_5_6_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
            assert needle not in source, (
                f"{path.name}: forbidden raw-secret-looking "
                f"literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# 7. Forbidden later-substage / public-routing identifier scan
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
    "dexscreener" + "_dispatch",
    "helius" + "_price",
    "bonding" + "_curve_decoder",
    "stage29_6" + "_",
    "stage_29_6" + "_",
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
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
    return idents


def test_no_stage_29_5_6_production_identifier_implements_forbidden_surface() -> None:
    for path in _iter_stage29_5_6_production_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{path.name}: forbidden identifier "
                    f"substring {needle!r} in identifier "
                    f"{ident!r}"
                )


# ---------------------------------------------------------------------------
# 8. No top-level Call (no implicit I/O at import time)
# ---------------------------------------------------------------------------


def _is_allowed_dataclass_decorator_call(
    call: ast.Call,
) -> bool:
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
        if isinstance(
            stmt, (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            scopes: list[tuple[str, list]] = [
                (
                    "function-decorator",
                    list(stmt.decorator_list),
                ),
                (
                    "function-arg-default",
                    list(stmt.args.defaults),
                ),
                (
                    "function-kw-default",
                    [
                        d
                        for d in stmt.args.kw_defaults
                        if d is not None
                    ],
                ),
            ]
            all_args = (
                list(stmt.args.args)
                + list(stmt.args.kwonlyargs)
                + list(
                    getattr(
                        stmt.args, "posonlyargs", [],
                    )
                )
            )
            for arg in all_args:
                if arg.annotation is not None:
                    scopes.append(
                        (
                            "function-arg-annotation",
                            [arg.annotation],
                        )
                    )
            if stmt.returns is not None:
                scopes.append(
                    (
                        "function-return-annotation",
                        [stmt.returns],
                    )
                )
            for label, nodes in scopes:
                for n in nodes:
                    for sub in ast.walk(n):
                        if isinstance(sub, ast.Call):
                            forbidden.append(
                                f"{stmt.name}@{label}:"
                                f"{ast.dump(sub.func)}"
                            )
        elif isinstance(stmt, ast.ClassDef):
            for d in stmt.decorator_list:
                if (
                    isinstance(d, ast.Call)
                    and _is_allowed_dataclass_decorator_call(
                        d,
                    )
                ):
                    continue
                for sub in ast.walk(d):
                    if isinstance(sub, ast.Call):
                        forbidden.append(
                            f"{stmt.name}@class-decorator:"
                            f"{ast.dump(sub.func)}"
                        )
            for b in stmt.bases:
                for sub in ast.walk(b):
                    if isinstance(sub, ast.Call):
                        forbidden.append(
                            f"{stmt.name}@class-base:"
                            f"{ast.dump(sub.func)}"
                        )
            for k in stmt.keywords:
                for sub in ast.walk(k.value):
                    if isinstance(sub, ast.Call):
                        forbidden.append(
                            f"{stmt.name}@class-keyword:"
                            f"{ast.dump(sub.func)}"
                        )
        else:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call):
                    forbidden.append(
                        f"{type(stmt).__name__}:"
                        f"{ast.dump(sub.func)}"
                    )
    return forbidden


def test_no_stage_29_5_6_production_has_module_body_calls_except_allowed_dataclass() -> None:
    for path in _iter_stage29_5_6_production_files():
        forbidden = _module_body_forbidden_calls(_read(path))
        assert not forbidden, (
            f"{path.name}: Stage 29.5.6 production must not "
            f"contain any module-body Call except "
            f"@dataclass(...) class decorators; offenders: "
            f"{forbidden!r}"
        )


# ---------------------------------------------------------------------------
# 9. Locked filter_enforcement_status token preserved
# ---------------------------------------------------------------------------


def test_locked_enforcement_token_preserved_in_manifest() -> None:
    src = _read(
        STAGE29_ROOT / "stage29_5_6_manifest.py"
    )
    assert (
        "STAGE29_5_6_FILTER_ENFORCEMENT_STATUS_LOCKED" in src
    )
    assert "NOT_ACTIVE_STAGE_29_PENDING" in src


# ---------------------------------------------------------------------------
# 10. Stage 29.3 imports zero stage29_5 modules (pin survives
# Stage 29.5.6)
# ---------------------------------------------------------------------------


def test_stage_29_3_production_imports_zero_stage29_5_modules() -> None:
    """Stage 29.3 mode-3 consumes the Stage 29.5.6 injector
    duck-typed via the new ``private_discord_body_injector``
    kwarg (annotated ``Optional[object]``). Stage 29.3
    production source must continue to import ZERO
    ``stage29_5*`` modules at runtime.
    """
    stage29_3_source_path = (
        STAGE29_ROOT / "stage29_3_tradeable_smoke.py"
    )
    targets = _collect_imported_module_paths(
        _read(stage29_3_source_path),
    )
    for target in targets:
        assert not target.startswith(
            "PHX2.stage29.stage29_5",
        ), (
            f"stage29_3_tradeable_smoke.py must not import "
            f"any stage29_5* module; offender: {target!r}"
        )


def test_stage_29_4_production_imports_zero_stage29_5_modules() -> None:
    """Stage 29.4 soak orchestrator must continue to import
    ZERO ``stage29_5*`` modules at runtime; Stage 29.5.6 does
    not modify Stage 29.4 production.
    """
    stage29_4_source_paths: tuple[Path, ...] = (
        STAGE29_ROOT / "stage29_4_soak_orchestrator.py",
        STAGE29_ROOT / "stage29_4_dedupe_index.py",
        STAGE29_ROOT / "stage29_4_soak_artifact_writer.py",
        STAGE29_ROOT / "stage29_4_manifest.py",
        STAGE29_ROOT / "stage29_4_soak_models.py",
    )
    for path in stage29_4_source_paths:
        if not path.is_file():
            continue
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert not target.startswith(
                "PHX2.stage29.stage29_5",
            ), (
                f"{path.name}: Stage 29.4 production must not "
                f"import any stage29_5* module; offender: "
                f"{target!r}"
            )


# ---------------------------------------------------------------------------
# 11. Stage 29.5 / 29.5.2 / 29.5.3 / 29.5.4 / 29.5.5 production
# inventories unchanged
# ---------------------------------------------------------------------------


_STAGE_29_5_LOCKED_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_migration_models.py",
    "stage29_5_helius_ws_adapter.py",
    "stage29_5_migration_artifact_reader.py",
    "stage29_5_candidate_to_migration_join.py",
    "stage29_5_private_ping_context_projection.py",
    "stage29_5_manifest.py",
)


_STAGE_29_5_2_LOCKED_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_2_offline_integration.py",
    "stage29_5_2_synthetic_evidence_fixtures.py",
    "stage29_5_2_manifest.py",
)


_STAGE_29_5_3_LOCKED_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_3_wrapped_pass_models.py",
    "stage29_5_3_soak_pass_wrapper.py",
    "stage29_5_3_side_channel_artifact_writer.py",
    "stage29_5_3_manifest.py",
)


_STAGE_29_5_4_LOCKED_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_4_migration_context_source_adapter.py",
    "stage29_5_4_manifest.py",
)


_STAGE_29_5_5_LOCKED_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_5_render_models.py",
    "stage29_5_5_private_discord_migration_context_renderer.py",
    "stage29_5_5_migration_context_recorder.py",
    "stage29_5_5_side_channel_artifact_writer.py",
    "stage29_5_5_manifest.py",
)


def test_stage_29_5_manifest_production_inventory_unchanged() -> None:
    from PHX2.stage29.stage29_5_manifest import (
        STAGE29_5_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_5_PRODUCTION_PY_BASENAMES
        == _STAGE_29_5_LOCKED_PRODUCTION_PY_BASENAMES
    )


def test_stage_29_5_2_manifest_production_inventory_unchanged() -> None:
    from PHX2.stage29.stage29_5_2_manifest import (
        STAGE29_5_2_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_5_2_PRODUCTION_PY_BASENAMES
        == _STAGE_29_5_2_LOCKED_PRODUCTION_PY_BASENAMES
    )


def test_stage_29_5_3_manifest_production_inventory_unchanged() -> None:
    from PHX2.stage29.stage29_5_3_manifest import (
        STAGE29_5_3_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_5_3_PRODUCTION_PY_BASENAMES
        == _STAGE_29_5_3_LOCKED_PRODUCTION_PY_BASENAMES
    )


def test_stage_29_5_4_manifest_production_inventory_unchanged() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_5_4_PRODUCTION_PY_BASENAMES
        == _STAGE_29_5_4_LOCKED_PRODUCTION_PY_BASENAMES
    )


def test_stage_29_5_5_manifest_production_inventory_unchanged() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_5_5_PRODUCTION_PY_BASENAMES
        == _STAGE_29_5_5_LOCKED_PRODUCTION_PY_BASENAMES
    )
