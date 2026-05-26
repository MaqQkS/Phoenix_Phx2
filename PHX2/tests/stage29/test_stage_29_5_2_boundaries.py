"""Stage 29.5.2 boundary scan.

Pins:

  * Every Stage 29.5.2 production .py / doc / test file exists at
    the locked path.
  * Stage 29.5.2 admits ZERO env-read sites.
  * Stage 29.5.2 admits ZERO outbound HTTP / WS / socket / gRPC
    imports across all production files.
  * Stage 29.5.2 production modules must NOT import any Stage
    21-26 module, any Stage 28 module, any Stage 29.1 / 29.2 /
    29.3 / 29.4 module, any forbidden runtime library, or any
    PHX1 / Phoenix_Bot path.
  * Stage 29.5.2 production code may import ONLY:
      - stdlib (``dataclasses`` / ``typing``),
      - ``PHX2.stage27.price_ath_context_models``,
      - ``PHX2.stage29.stage29_5_migration_models``,
      - ``PHX2.stage29.stage29_5_candidate_to_migration_join``,
      - ``PHX2.stage29.stage29_5_private_ping_context_projection``,
      - sibling ``PHX2.stage29.stage29_5_2_*`` modules.
  * Stage 29.5.2 production source carries NO PHX1 substring, NO
    Pump.fun bonding-curve program id literal, NO URL host
    literal, NO raw-secret-looking literal.
  * The bare string literal ``"SYNTHETIC_TEST_ONLY"`` (or its
    single-quoted equivalent) may appear ONLY in
    ``stage29_5_2_synthetic_evidence_fixtures.py`` -- the Stage
    29.5.2 admitted-synthetic-token file. The composition module
    and the manifest must never carry the bare literal.
  * Stage 29.5.2 production modules contain NO top-level Call.
  * Stage 29.5.2 production identifiers do not implement any
    forbidden later-substage / public-routing / social / trading
    surface.
  * The Stage 29.5.2 manifest pins the same inventories the
    boundary scan asserts.
  * The locked filter_enforcement_status token
    NOT_ACTIVE_STAGE_29_PENDING is preserved verbatim.
  * The Stage 29.5 manifest production inventory is unchanged.
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


_STAGE_29_5_2_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_2_offline_integration.py",
    "stage29_5_2_synthetic_evidence_fixtures.py",
    "stage29_5_2_manifest.py",
)


_STAGE_29_5_2_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_2_OFFLINE_INTEGRATION_PROOF_RUNBOOK.md",
)


_STAGE_29_5_2_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_2_offline_integration.py",
    "test_stage_29_5_2_boundaries.py",
    "test_stage_29_5_2_no_integration_into_stage_29_3.py",
    "test_stage_29_5_2_manifest.py",
    "test_stage_29_5_2_spec_lock.py",
)


# Stage 29.5.2 production code is admitted to import these
# external surfaces and nothing else (besides stdlib + sibling
# stage29_5_2_* modules).
_ADMITTED_EXTERNAL_PHX2_IMPORT_PREFIXES: tuple[str, ...] = (
    "PHX2.stage27.price_ath_context_models",
    "PHX2.stage29.stage29_5_migration_models",
    "PHX2.stage29.stage29_5_candidate_to_migration_join",
    "PHX2.stage29.stage29_5_private_ping_context_projection",
)


# Synthetic-source bare-literal admission list. Only the fixtures
# module is allowed to carry the bare literal (in fact it does
# not need to either, since the Stage 29.5 model exposes the
# token as a symbolic constant; but this list pins the discipline
# in case future rewrites inline the literal).
_SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES: tuple[str, ...] = (
    "stage29_5_2_synthetic_evidence_fixtures.py",
)


def _iter_stage29_5_2_production_files() -> list[Path]:
    return [
        STAGE29_ROOT / name
        for name in _STAGE_29_5_2_PRODUCTION_PY_BASENAMES
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


def test_every_stage_29_5_2_production_py_file_exists():
    for name in _STAGE_29_5_2_PRODUCTION_PY_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.5.2 requires production .py file {path}"
        )


def test_every_stage_29_5_2_doc_file_exists():
    for name in _STAGE_29_5_2_DOC_BASENAMES:
        path = STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.5.2 requires doc {path}"
        )


def test_every_stage_29_5_2_test_file_exists():
    for name in _STAGE_29_5_2_TEST_BASENAMES:
        path = TESTS_STAGE29_ROOT / name
        assert path.is_file(), (
            f"Stage 29.5.2 requires test {path}"
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


def test_no_stage_29_5_2_production_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage29_5_2_production_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 29.5.2 admits ZERO env-read sites; offenders: "
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


def test_no_stage_29_5_2_production_imports_outbound_network():
    for path in _iter_stage29_5_2_production_files():
        hits = _module_imports_any(
            _read(path), _OUTBOUND_NETWORK_IMPORT_PATTERNS
        )
        assert not hits, (
            f"{path.name}: Stage 29.5.2 admits ZERO outbound-"
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


def test_no_stage_29_5_2_production_imports_prior_stages():
    for path in _iter_stage29_5_2_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in (
                _FORBIDDEN_PRIOR_STAGE_PREFIXES
            ):
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden prior-stage "
                    f"import {target!r}"
                )


def test_no_stage_29_5_2_production_imports_stage_28():
    for path in _iter_stage29_5_2_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert not target.startswith("PHX2.stage28."), (
                f"{path.name}: Stage 29.5.2 must not import "
                f"any Stage 28 module; offender {target!r}"
            )
            assert target != "PHX2.stage28", (
                f"{path.name}: Stage 29.5.2 must not import "
                f"Stage 28 package directly"
            )


def test_no_stage_29_5_2_production_imports_forbidden_stage_29_siblings():
    """Stage 29.5.2 must not reach into Stage 29.0 / 29.1 / 29.2
    / 29.3 / 29.4 internal surfaces. Stage 29.5.2 imports only
    Stage 29.5 surfaces (the join / projection / models) and
    sibling Stage 29.5.2 modules.
    """
    forbidden_stage_29_prefixes: tuple[str, ...] = (
        "PHX2.stage29.stage29_0_",
        "PHX2.stage29.stage29_1_",
        "PHX2.stage29.stage29_2_",
        "PHX2.stage29.stage29_3_",
        "PHX2.stage29.stage29_4_",
    )
    for path in _iter_stage29_5_2_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for prefix in forbidden_stage_29_prefixes:
                assert not target.startswith(prefix), (
                    f"{path.name}: forbidden Stage 29.x "
                    f"sibling import {target!r}"
                )


def test_stage_29_5_2_production_only_imports_admitted_external_phx2():
    """Stage 29.5.2 production code's PHX2 imports are restricted
    to the admitted external prefix list plus sibling
    stage29_5_2_* modules.
    """
    admitted_with_dot = tuple(
        prefix + "."
        for prefix in _ADMITTED_EXTERNAL_PHX2_IMPORT_PREFIXES
    )
    for path in _iter_stage29_5_2_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if not target.startswith("PHX2."):
                continue
            if target.startswith(
                "PHX2.stage29.stage29_5_2_"
            ):
                continue
            ok = target in (
                _ADMITTED_EXTERNAL_PHX2_IMPORT_PREFIXES
            ) or any(
                target.startswith(prefix)
                for prefix in admitted_with_dot
            )
            assert ok, (
                f"{path.name}: PHX2 import {target!r} not in "
                "Stage 29.5.2 admitted-external allowlist"
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


def test_no_stage_29_5_2_production_imports_forbidden_runtime():
    for path in _iter_stage29_5_2_production_files():
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


def test_no_stage_29_5_2_production_imports_phx1():
    for path in _iter_stage29_5_2_production_files():
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


def test_no_stage_29_5_2_production_source_carries_phx1_path():
    for path in _iter_stage29_5_2_production_files():
        source = _read(path)
        lower = source.lower()
        assert "phoenix_bot" not in lower, (
            f"{path.name}: forbidden 'Phoenix_Bot' substring"
        )


def test_no_stage_29_5_2_production_carries_pump_fun_program_id():
    for path in _iter_stage29_5_2_production_files():
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


def test_no_url_host_literal_in_stage_29_5_2_production_source():
    for path in _iter_stage29_5_2_production_files():
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


def test_no_raw_secret_literal_in_stage_29_5_2_production_source():
    for path in _iter_stage29_5_2_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
            assert needle not in source, (
                f"{path.name}: forbidden raw-secret-looking "
                f"literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# 7. Synthetic-source token bare-literal scope guard
# ---------------------------------------------------------------------------


def test_bare_synthetic_source_literal_admitted_only_on_fixtures():
    """The bare string literal ``"SYNTHETIC_TEST_ONLY"`` (or its
    single-quoted equivalent) may appear ONLY in the Stage 29.5.2
    synthetic evidence fixtures module. The composition module
    and the manifest must reference the symbolic Stage 29.5
    constant rather than the bare literal.
    """
    bare_double = '"SYNTHETIC_TEST_ONLY"'
    bare_single = "'SYNTHETIC_TEST_ONLY'"
    for path in _iter_stage29_5_2_production_files():
        source = _read(path)
        if path.name in (
            _SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES
        ):
            continue
        assert bare_double not in source, (
            f"{path.name}: must not carry bare "
            f"{bare_double!r} literal; only "
            f"{_SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES!r} "
            f"may carry it"
        )
        assert bare_single not in source, (
            f"{path.name}: must not carry bare "
            f"{bare_single!r} literal; only "
            f"{_SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES!r} "
            f"may carry it"
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
    "stage29_5_3" + "_",
    "soak_pass_wrapper",
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


def test_no_stage_29_5_2_production_identifier_implements_forbidden_surface():
    for path in _iter_stage29_5_2_production_files():
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
# 9. No top-level Call / no implicit I/O at import time
# ---------------------------------------------------------------------------


def _has_top_level_call(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            return True
    return False


def test_no_stage_29_5_2_production_has_top_level_call():
    for path in _iter_stage29_5_2_production_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path.name}: Stage 29.5.2 production must not "
            f"contain top-level Call (no implicit I/O at "
            f"import time)"
        )


# ---------------------------------------------------------------------------
# 10. Locked filter_enforcement_status token preserved
# ---------------------------------------------------------------------------


def test_locked_enforcement_token_preserved_in_composition():
    src = _read(
        STAGE29_ROOT / "stage29_5_2_offline_integration.py"
    )
    assert (
        "FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING"
        in src
    )


def test_locked_enforcement_token_preserved_in_manifest():
    src = _read(STAGE29_ROOT / "stage29_5_2_manifest.py")
    assert (
        "STAGE29_5_2_FILTER_ENFORCEMENT_STATUS_LOCKED" in src
    )


# ---------------------------------------------------------------------------
# 11. Stage 29.5.2 manifest pin sanity (cross-check)
# ---------------------------------------------------------------------------


def test_manifest_pins_production_inventory():
    from PHX2.stage29.stage29_5_2_manifest import (
        STAGE29_5_2_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_5_2_PRODUCTION_PY_BASENAMES
        == _STAGE_29_5_2_PRODUCTION_PY_BASENAMES
    )


def test_manifest_pins_doc_inventory():
    from PHX2.stage29.stage29_5_2_manifest import (
        STAGE29_5_2_DOC_BASENAMES,
    )
    assert (
        STAGE29_5_2_DOC_BASENAMES == _STAGE_29_5_2_DOC_BASENAMES
    )


def test_manifest_pins_test_inventory():
    from PHX2.stage29.stage29_5_2_manifest import (
        STAGE29_5_2_TEST_BASENAMES,
    )
    assert (
        STAGE29_5_2_TEST_BASENAMES
        == _STAGE_29_5_2_TEST_BASENAMES
    )


def test_manifest_pins_zero_env_read_admission():
    from PHX2.stage29.stage29_5_2_manifest import (
        STAGE29_5_2_ENV_READ_ADMITTED_BASENAMES,
    )
    assert STAGE29_5_2_ENV_READ_ADMITTED_BASENAMES == ()


def test_manifest_pins_zero_outbound_network_admission():
    from PHX2.stage29.stage29_5_2_manifest import (
        STAGE29_5_2_OUTBOUND_NETWORK_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_5_2_OUTBOUND_NETWORK_ADMITTED_BASENAMES == ()
    )


def test_manifest_pins_synthetic_source_token_admission():
    from PHX2.stage29.stage29_5_2_manifest import (
        STAGE29_5_2_SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_5_2_SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES
        == _SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES
    )


# ---------------------------------------------------------------------------
# 12. Stage 29.5 manifest production inventory unchanged
# ---------------------------------------------------------------------------


_STAGE_29_5_LOCKED_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_migration_models.py",
    "stage29_5_helius_ws_adapter.py",
    "stage29_5_migration_artifact_reader.py",
    "stage29_5_candidate_to_migration_join.py",
    "stage29_5_private_ping_context_projection.py",
    "stage29_5_manifest.py",
)


def test_stage_29_5_manifest_production_inventory_unchanged():
    """Stage 29.5.2 must NOT mutate the Stage 29.5 manifest's
    production-inventory tuple. The 6-file Stage 29.5 inventory
    is locked at Stage 29.5.1 and survives Stage 29.5.2.
    """
    from PHX2.stage29.stage29_5_manifest import (
        STAGE29_5_PRODUCTION_PY_BASENAMES,
    )
    assert (
        STAGE29_5_PRODUCTION_PY_BASENAMES
        == _STAGE_29_5_LOCKED_PRODUCTION_PY_BASENAMES
    )


def test_stage_29_5_manifest_env_read_admission_still_empty():
    from PHX2.stage29.stage29_5_manifest import (
        STAGE29_5_ENV_READ_ADMITTED_BASENAMES,
    )
    assert STAGE29_5_ENV_READ_ADMITTED_BASENAMES == ()


def test_stage_29_5_manifest_outbound_network_admission_still_empty():
    from PHX2.stage29.stage29_5_manifest import (
        STAGE29_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES == ()
    )


# ---------------------------------------------------------------------------
# 13. Composition module imports the Stage 29.5 + Stage 27.4
#     surfaces exactly (no extra Stage imports leaked in)
# ---------------------------------------------------------------------------


def test_composition_module_imports_only_admitted_surfaces():
    src = _read(
        STAGE29_ROOT / "stage29_5_2_offline_integration.py"
    )
    targets = _collect_imported_module_paths(src)
    phx2_targets = {
        t for t in targets if t.startswith("PHX2.")
    }
    expected_phx2_imports = {
        "PHX2.stage27.price_ath_context_models",
        "PHX2.stage29.stage29_5_candidate_to_migration_join",
        "PHX2.stage29.stage29_5_migration_models",
        "PHX2.stage29.stage29_5_private_ping_context_projection",
    }
    assert phx2_targets == expected_phx2_imports, (
        "stage29_5_2_offline_integration.py: PHX2 imports must "
        f"equal {sorted(expected_phx2_imports)!r}; got "
        f"{sorted(phx2_targets)!r}"
    )


def test_fixtures_module_imports_only_stage_29_5_models():
    src = _read(
        STAGE29_ROOT
        / "stage29_5_2_synthetic_evidence_fixtures.py"
    )
    targets = _collect_imported_module_paths(src)
    phx2_targets = {
        t for t in targets if t.startswith("PHX2.")
    }
    expected_phx2_imports = {
        "PHX2.stage29.stage29_5_migration_models",
    }
    assert phx2_targets == expected_phx2_imports, (
        "stage29_5_2_synthetic_evidence_fixtures.py: PHX2 "
        "imports must equal "
        f"{sorted(expected_phx2_imports)!r}; got "
        f"{sorted(phx2_targets)!r}"
    )


def test_manifest_module_imports_only_admitted_surfaces():
    src = _read(STAGE29_ROOT / "stage29_5_2_manifest.py")
    targets = _collect_imported_module_paths(src)
    phx2_targets = {
        t for t in targets if t.startswith("PHX2.")
    }
    expected_phx2_imports = {
        "PHX2.stage29.stage29_5_2_offline_integration",
        "PHX2.stage29.stage29_5_2_synthetic_evidence_fixtures",
        "PHX2.stage29.stage29_5_migration_models",
    }
    assert phx2_targets == expected_phx2_imports, (
        "stage29_5_2_manifest.py: PHX2 imports must equal "
        f"{sorted(expected_phx2_imports)!r}; got "
        f"{sorted(phx2_targets)!r}"
    )


# ---------------------------------------------------------------------------
# 14. Stronger module-body Call scan
# ---------------------------------------------------------------------------
#
# The simpler ``_has_top_level_call`` scan above only catches bare
# expression statements at module level whose value is a Call (the
# canonical ``foo()`` line at the top of a file). It misses Calls
# embedded in module-body assignments, AnnAssign values, decorators,
# parameter / return type annotations, and default values. Those
# also execute at import time and could open a network connection,
# read an env var, or write a file.
#
# This stronger scan walks every module-body statement, descends
# into decorator lists / annotations / default values / class bases
# / class keywords / assignment RHS expressions, but explicitly does
# NOT descend into ``FunctionDef`` / ``AsyncFunctionDef`` / ``ClassDef``
# bodies (those are deferred-execution scopes). The only allowed
# top-level Call is the ``@dataclass(...)`` decorator on a ClassDef.


def _is_allowed_dataclass_decorator_call(call: ast.Call) -> bool:
    """Return True iff ``call`` is a ``@dataclass(...)`` decorator
    call.

    Matches both ``from dataclasses import dataclass`` (Name) and
    ``import dataclasses`` (Attribute) usage. The decorator may take
    any keyword args (``frozen=True``, ``slots=True``, etc.) -- the
    arguments are not constrained because they cannot perform I/O.
    """
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
    """Return a list of human-readable descriptors for every
    forbidden module-body Call.

    Walks every module-body statement; descends into decorators /
    annotations / default values / class bases / class keywords /
    assignment RHS expressions; does NOT descend into FunctionDef /
    AsyncFunctionDef / ClassDef bodies. ``@dataclass(...)`` class
    decorator calls are admitted via
    :func:`_is_allowed_dataclass_decorator_call`.

    Returns an empty list when the module body is Call-free at
    import time (modulo the allowed dataclass decorator pattern).
    """
    tree = ast.parse(source)
    forbidden: list[str] = []
    for stmt in tree.body:
        if isinstance(
            stmt, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            scopes: list[tuple[str, list]] = [
                ("function-decorator", list(stmt.decorator_list)),
                ("function-arg-default", list(stmt.args.defaults)),
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
                + list(getattr(stmt.args, "posonlyargs", []))
            )
            for arg in all_args:
                if arg.annotation is not None:
                    scopes.append(
                        ("function-arg-annotation", [arg.annotation])
                    )
            if stmt.returns is not None:
                scopes.append(
                    ("function-return-annotation", [stmt.returns])
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
                if isinstance(
                    d, ast.Call
                ) and _is_allowed_dataclass_decorator_call(d):
                    # The dataclass(...) decorator Call itself is
                    # admitted; do not descend into its keyword arg
                    # values either, because those are constant
                    # literals like frozen=True / slots=True.
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
            # Any other top-level statement: walk its entire subtree
            # for Call nodes. This catches bare expressions, Assign,
            # AnnAssign, AugAssign, If/For/While at module level,
            # etc.
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call):
                    forbidden.append(
                        f"{type(stmt).__name__}:"
                        f"{ast.dump(sub.func)}"
                    )
    return forbidden


def test_no_stage_29_5_2_production_has_module_body_calls_except_allowed_dataclass():
    """Stage 29.5.2 production modules must remain offline / no-I/O
    at import time.

    Stronger than the earlier bare-expression scan: this walks every
    module-body statement (assignments, annotations, decorators,
    default values, class bases, class keywords) and forbids ALL
    Call nodes EXCEPT the ``@dataclass(...)`` class-decorator
    pattern.
    """
    for path in _iter_stage29_5_2_production_files():
        forbidden = _module_body_forbidden_calls(_read(path))
        assert not forbidden, (
            f"{path.name}: Stage 29.5.2 production must not "
            f"contain any module-body Call except "
            f"@dataclass(...) class decorators; offenders: "
            f"{forbidden!r}"
        )


# ---------------------------------------------------------------------------
# 15. Synthetic-fixtures import scope
# ---------------------------------------------------------------------------
#
# The Stage 29.5.2 synthetic evidence fixtures module is the sole
# authorized site for the ``MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY``
# token at the Stage 29.5.2 inventory boundary. It must remain
# offline / test / proof scoped: production code (anywhere under
# ``PHX2/`` outside ``PHX2/tests/``) must not import it except from
# the Stage 29.5.2 manifest, which re-exports the builder names as
# inert sentinel references for the boundary scan.


_STAGE29_5_2_FIXTURES_MODULE_BASENAME: str = (
    "stage29_5_2_synthetic_evidence_fixtures.py"
)


_STAGE29_5_2_FIXTURES_ADMITTED_PRODUCTION_IMPORTERS: tuple[
    str, ...
] = ("stage29_5_2_manifest.py",)


_STAGE29_5_2_FIXTURES_MODULE_DOTTED_NAMES: tuple[str, ...] = (
    "PHX2.stage29.stage29_5_2_synthetic_evidence_fixtures",
)


def _file_imports_stage29_5_2_fixtures(path: Path) -> bool:
    try:
        source = _read(path)
    except OSError:
        return False
    try:
        targets = _collect_imported_module_paths(source)
    except SyntaxError:
        return False
    for target in targets:
        if target in _STAGE29_5_2_FIXTURES_MODULE_DOTTED_NAMES:
            return True
        if target.endswith(
            ".stage29_5_2_synthetic_evidence_fixtures"
        ):
            return True
    return False


def _iter_all_phx2_production_py_files() -> list[Path]:
    """Yield every .py file under ``PHX2/`` that is NOT a test and
    NOT under a ``__pycache__`` directory. Used to scan for cross-
    stage imports of the Stage 29.5.2 synthetic fixtures module.
    """
    results: list[Path] = []
    for entry in PHX2_ROOT.rglob("*.py"):
        try:
            relative = entry.relative_to(PHX2_ROOT)
        except ValueError:
            continue
        parts = relative.parts
        if not parts:
            continue
        if parts[0] == "tests":
            continue
        if "__pycache__" in parts:
            continue
        results.append(entry)
    return results


def test_stage_29_5_2_synthetic_fixtures_imported_only_by_manifest_and_tests():
    """The Stage 29.5.2 synthetic evidence fixtures module must
    remain offline / test / proof scoped. Production code anywhere
    under ``PHX2/`` (excluding ``PHX2/tests/``) must NOT import it
    except from the Stage 29.5.2 manifest, which intentionally
    re-exports the builder names as inert sentinel references for
    the boundary scan.

    Tests under ``PHX2/tests/`` are not scanned; tests may freely
    import the fixtures module.
    """
    offenders: list[str] = []
    for path in _iter_all_phx2_production_py_files():
        if path.name == _STAGE29_5_2_FIXTURES_MODULE_BASENAME:
            continue
        if path.name in (
            _STAGE29_5_2_FIXTURES_ADMITTED_PRODUCTION_IMPORTERS
        ):
            continue
        if _file_imports_stage29_5_2_fixtures(path):
            offenders.append(
                str(path.relative_to(PHX2_ROOT))
            )
    assert not offenders, (
        f"Stage 29.5.2 synthetic fixtures module must remain "
        f"test / proof scoped. PHX2 production files allowed to "
        f"import it: "
        f"{_STAGE29_5_2_FIXTURES_ADMITTED_PRODUCTION_IMPORTERS!r}. "
        f"Offenders: {sorted(offenders)!r}"
    )


def test_stage_29_3_production_does_not_import_synthetic_fixtures():
    """Stage 29.3 mode-3 orchestrator + sibling Stage 29.3
    production files must not import the Stage 29.5.2 synthetic
    fixtures module. Pinned alongside the broader scan above for
    defense in depth.
    """
    for path in STAGE29_ROOT.glob("stage29_3*.py"):
        if not path.is_file():
            continue
        assert not _file_imports_stage29_5_2_fixtures(path), (
            f"{path.name}: Stage 29.3 production must not import "
            f"the Stage 29.5.2 synthetic fixtures module"
        )


def test_stage_29_4_production_does_not_import_synthetic_fixtures():
    """Stage 29.4 soak orchestrator + sibling Stage 29.4 production
    files must not import the Stage 29.5.2 synthetic fixtures
    module.
    """
    for path in STAGE29_ROOT.glob("stage29_4*.py"):
        if not path.is_file():
            continue
        assert not _file_imports_stage29_5_2_fixtures(path), (
            f"{path.name}: Stage 29.4 production must not import "
            f"the Stage 29.5.2 synthetic fixtures module"
        )


def test_stage_29_5_production_does_not_import_synthetic_fixtures():
    """Stage 29.5 production tree (the locked six-file inventory)
    must not import the Stage 29.5.2 synthetic fixtures module.
    The Stage 29.5 production code is offline / synthetic-token-
    free; cross-stage proliferation of the synthetic token would
    erode that invariant.
    """
    stage29_5_production = (
        "stage29_5_migration_models.py",
        "stage29_5_helius_ws_adapter.py",
        "stage29_5_migration_artifact_reader.py",
        "stage29_5_candidate_to_migration_join.py",
        "stage29_5_private_ping_context_projection.py",
        "stage29_5_manifest.py",
    )
    for basename in stage29_5_production:
        path = STAGE29_ROOT / basename
        if not path.is_file():
            continue
        assert not _file_imports_stage29_5_2_fixtures(path), (
            f"{basename}: Stage 29.5 production must not import "
            f"the Stage 29.5.2 synthetic fixtures module"
        )


def test_stage_29_5_2_composition_does_not_import_synthetic_fixtures():
    """The Stage 29.5.2 composition module
    (``stage29_5_2_offline_integration.py``) must not import the
    fixtures module. The composition is generic over caller-
    supplied evidence; fixtures live alongside but never inside the
    composition's runtime surface.
    """
    composition_path = (
        STAGE29_ROOT / "stage29_5_2_offline_integration.py"
    )
    assert composition_path.is_file()
    assert not _file_imports_stage29_5_2_fixtures(
        composition_path
    ), (
        "stage29_5_2_offline_integration.py: composition module "
        "must not import the synthetic fixtures; the fixtures are "
        "exclusively test / proof scoped"
    )
