"""Stage 29.5 boundary scan.

Pins:

  * Every Stage 29.5 production .py / doc / test file exists at
    the locked path.
  * Stage 29.5 admits ZERO env-read sites.
  * Stage 29.5 admits ZERO outbound HTTP / WS / socket / gRPC
    imports across all production files.
  * Stage 29.5 production modules must NOT import any Stage
    21-26 module, any forbidden runtime library, or any PHX1 /
    Phoenix_Bot path.
  * Stage 29.5 production source carries NO PHX1 substring, NO
    Pump.fun bonding-curve program id literal, NO URL host
    literal, NO raw-secret-looking literal.
  * Stage 29.5 Helius WS adapter + artifact reader production
    files must NEVER carry the synthetic-source token as a
    runtime output literal (the token is admitted at the model
    layer for tests, but production code paths must not emit
    it).
  * Stage 29.5 production modules contain NO top-level Call.
  * The Stage 29.5 manifest pins the same inventories the
    boundary scan asserts.
  * The locked filter_enforcement_status token
    NOT_ACTIVE_STAGE_29_PENDING is preserved verbatim.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"


_STAGE_29_5_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_migration_models.py",
    "stage29_5_helius_ws_adapter.py",
    "stage29_5_migration_artifact_reader.py",
    "stage29_5_candidate_to_migration_join.py",
    "stage29_5_private_ping_context_projection.py",
    "stage29_5_manifest.py",
)


_STAGE_29_5_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md",
)


_STAGE_29_5_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_migration_models.py",
    "test_stage_29_5_helius_ws_adapter.py",
    "test_stage_29_5_migration_artifact_reader.py",
    "test_stage_29_5_candidate_to_migration_join.py",
    "test_stage_29_5_private_ping_context_projection.py",
    "test_stage_29_5_manifest.py",
    "test_stage_29_5_boundaries.py",
    "test_stage_29_5_spec_lock.py",
)


# Stage 29.5 admits Stage 27.4 read-only model imports only on
# the projection module. Models, adapter, reader, join, and
# manifest must not import any Stage 27 surface.
_STAGE_27_ADMITTED_FOR_PROJECTION: tuple[str, ...] = (
    "PHX2.stage27.price_ath_context_models",
)


def _iter_stage29_5_production_files() -> list[Path]:
    return [
        STAGE29_ROOT / name
        for name in _STAGE_29_5_PRODUCTION_PY_BASENAMES
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


def test_every_stage_29_5_production_py_file_exists():
    for name in _STAGE_29_5_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.5 requires production .py file {path}"
        )


def test_every_stage_29_5_doc_file_exists():
    for name in _STAGE_29_5_DOC_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.5 requires doc {path}"
        )


def test_every_stage_29_5_test_file_exists():
    for name in _STAGE_29_5_TEST_BASENAMES:
        path = TESTS_STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.5 requires test {path}"
        )


# ---------------------------------------------------------------------------
# 2. Env-read isolation (ZERO env-read sites)
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


def test_no_stage_29_5_production_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage29_5_production_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 29.5 admits ZERO env-read sites; offenders: "
        f"{leaked!r}"
    )


# ---------------------------------------------------------------------------
# 3. Outbound-network isolation (ZERO sites)
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


def test_no_stage_29_5_production_imports_outbound_network():
    for path in _iter_stage29_5_production_files():
        hits = _module_imports_any(
            _read(path), _OUTBOUND_NETWORK_IMPORT_PATTERNS
        )
        assert not hits, (
            f"{path.name}: Stage 29.5 admits ZERO outbound-"
            f"network imports; offenders: {sorted(hits)!r}"
        )


# ---------------------------------------------------------------------------
# 4. No forbidden prior-stage imports
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
)


def test_no_stage_29_5_production_imports_prior_stages():
    for path in _iter_stage29_5_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in (
                _FORBIDDEN_PRIOR_STAGE_PREFIXES
            ):
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden prior-stage "
                    f"import {target!r}"
                )


def test_stage_29_5_production_only_imports_authorized_stage_27():
    """Stage 29.5 production code only touches Stage 27 from the
    projection module, which reads ``AthContextRecord`` as a
    type shape. All other Stage 29.5 modules stay Stage-27-free.
    """
    for path in _iter_stage29_5_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if not target.startswith("PHX2.stage27"):
                continue
            if path.name == (
                "stage29_5_private_ping_context_projection.py"
            ):
                ok = target in (
                    _STAGE_27_ADMITTED_FOR_PROJECTION
                ) or any(
                    target.startswith(prefix + ".")
                    for prefix in (
                        _STAGE_27_ADMITTED_FOR_PROJECTION
                    )
                )
                assert ok, (
                    f"{path.name}: stage27 import {target!r} "
                    f"not in projection-module allowlist"
                )
            else:
                pytest.fail(
                    f"{path.name}: stage27 import {target!r} "
                    f"is only admitted on the projection module"
                )


_FORBIDDEN_STAGE_28_IMPORTS: tuple[str, ...] = (
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
    "PHX2.stage28.chainstack_yellowstone_grpc_readiness",
    "PHX2.stage28.chainstack_yellowstone_grpc_decode",
    "PHX2.stage28.chainstack_yellowstone_grpc_models",
    "PHX2.stage28.chainstack_yellowstone_models",
)


def test_no_stage_29_5_production_imports_stage_28():
    for path in _iter_stage29_5_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert (
                target not in _FORBIDDEN_STAGE_28_IMPORTS
            ), (
                f"{path.name}: Stage 29.5 must not import "
                f"Stage 28 surface {target!r}"
            )
            assert not target.startswith(
                "PHX2.stage28."
            ), (
                f"{path.name}: Stage 29.5 must not import any "
                f"Stage 28 module; offender {target!r}"
            )


def test_no_stage_29_5_production_imports_sibling_stage_29_internals():
    """Stage 29.5 must not reach into Stage 29.1 / 29.2 / 29.3 /
    29.4 internal surfaces. The Stage 29.5 tree is self-contained
    aside from the Stage 27.4 model import on the projection.
    """
    for path in _iter_stage29_5_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if not target.startswith("PHX2.stage29."):
                continue
            if target.startswith("PHX2.stage29.stage29_5_"):
                continue
            pytest.fail(
                f"{path.name}: forbidden Stage 29 sibling "
                f"import {target!r}"
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


def test_no_stage_29_5_production_imports_forbidden_runtime():
    for path in _iter_stage29_5_production_files():
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


def test_no_stage_29_5_production_imports_phx1():
    for path in _iter_stage29_5_production_files():
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


def test_no_stage_29_5_production_source_carries_phx1_path():
    for path in _iter_stage29_5_production_files():
        source = _read(path)
        lower = source.lower()
        assert "phoenix_bot" not in lower, (
            f"{path.name}: forbidden 'Phoenix_Bot' substring"
        )


def test_no_stage_29_5_production_carries_pump_fun_program_id():
    for path in _iter_stage29_5_production_files():
        source = _read(path)
        assert (
            "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
            not in source
        ), (
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
    "ws" + "s://",
    "ws" + "://",
)


def test_no_url_host_literal_in_stage_29_5_production_source():
    for path in _iter_stage29_5_production_files():
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
    "HELIUS_WS" + "_URL=",
    "HELIUS_WS" + "_ENDPOINT=",
    "BIRDEYE_API" + "_KEY=",
    "CHAINSTACK_API" + "_KEY=",
)


def test_no_raw_secret_literal_in_stage_29_5_production_source():
    for path in _iter_stage29_5_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
            assert needle not in source, (
                f"{path.name}: forbidden raw-secret-looking "
                f"literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# 7. Synthetic-source token must not appear as runtime output on
#    the WS adapter or artifact reader production files.
# ---------------------------------------------------------------------------


_SYNTHETIC_GUARD_BASENAMES: tuple[str, ...] = (
    "stage29_5_helius_ws_adapter.py",
    "stage29_5_migration_artifact_reader.py",
)


def test_adapter_and_reader_do_not_emit_synthetic_source_value():
    """The string ``SYNTHETIC_TEST_ONLY`` may appear in the
    adapter / reader source ONLY in import statements or guard
    constants (e.g. the artifact reader's
    ``REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED`` guard which
    references the imported model constant). The token must
    NEVER appear as a string literal that the production code
    emits as a record's ``migration_source`` value.
    """
    for basename in _SYNTHETIC_GUARD_BASENAMES:
        source = _read(STAGE29_ROOT / basename)
        # The production source must not contain the bare string
        # literal ``"SYNTHETIC_TEST_ONLY"``. Symbolic references
        # (``MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY``) ARE allowed
        # because the adapter uses the symbol to GUARD against
        # the value, not to emit it.
        bare_literal = '"SYNTHETIC_TEST_ONLY"'
        assert bare_literal not in source, (
            f"{basename}: must not carry bare "
            f"{bare_literal!r} literal as a record output value"
        )
        bare_literal_single = "'SYNTHETIC_TEST_ONLY'"
        assert bare_literal_single not in source, (
            f"{basename}: must not carry bare "
            f"{bare_literal_single!r} literal as a record "
            f"output value"
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


def test_no_stage_29_5_production_identifier_implements_forbidden_surface():
    for path in _iter_stage29_5_production_files():
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
# 9. No top-level Call / filesystem-write
# ---------------------------------------------------------------------------


def _has_top_level_call(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            return True
    return False


def test_no_stage_29_5_production_has_top_level_call():
    for path in _iter_stage29_5_production_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path.name}: Stage 29.5 production must not "
            f"contain top-level Call (no implicit I/O at "
            f"import time)"
        )


# ---------------------------------------------------------------------------
# 10. Locked filter_enforcement_status token
# ---------------------------------------------------------------------------


def test_locked_enforcement_token_preserved_in_models():
    src = _read(
        STAGE29_ROOT / "stage29_5_migration_models.py"
    )
    assert (
        '"NOT_ACTIVE_STAGE_29_PENDING"' in src
        or "'NOT_ACTIVE_STAGE_29_PENDING'" in src
    )


def test_locked_enforcement_token_preserved_in_projection():
    src = _read(
        STAGE29_ROOT
        / "stage29_5_private_ping_context_projection.py"
    )
    # The projection imports the constant via name; the literal
    # is in the models module. Here we verify the projection
    # references the constant identifier.
    assert (
        "FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING"
        in src
    )


# ---------------------------------------------------------------------------
# 11. Manifest pin sanity (cross-check)
# ---------------------------------------------------------------------------


def test_manifest_pins_production_inventory():
    from PHX2.stage29.stage29_5_manifest import (
        STAGE29_5_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_5_PRODUCTION_PY_BASENAMES
        == _STAGE_29_5_PRODUCTION_PY_BASENAMES
    )


def test_manifest_pins_doc_inventory():
    from PHX2.stage29.stage29_5_manifest import (
        STAGE29_5_DOC_BASENAMES,
    )
    assert STAGE29_5_DOC_BASENAMES == _STAGE_29_5_DOC_BASENAMES


def test_manifest_pins_test_inventory():
    from PHX2.stage29.stage29_5_manifest import (
        STAGE29_5_TEST_BASENAMES,
    )
    assert (
        STAGE29_5_TEST_BASENAMES == _STAGE_29_5_TEST_BASENAMES
    )


def test_manifest_pins_zero_env_read_admission():
    from PHX2.stage29.stage29_5_manifest import (
        STAGE29_5_ENV_READ_ADMITTED_BASENAMES,
    )
    assert STAGE29_5_ENV_READ_ADMITTED_BASENAMES == ()


def test_manifest_pins_zero_outbound_network_admission():
    from PHX2.stage29.stage29_5_manifest import (
        STAGE29_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES == ()
    )
