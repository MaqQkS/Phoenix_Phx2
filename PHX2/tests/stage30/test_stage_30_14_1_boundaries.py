"""Stage 30.14.1 evidence-loader + replay-verifier boundary tests.

Scans the Stage 30.14.1 scanned production modules (data-driven from the manifest) for the
TWO-TIER discipline:

  * a per-tier stdlib import allowlist -- STRICT (``__future__`` / ``typing`` /
    ``dataclasses``) for the models leaf + the verifier; RELAXED (the strict set PLUS
    ``json`` + ``pathlib``) for the one read-only-filesystem loader;
  * a per-module PHX2 import allowlist (models = pure leaf; loader = models + the one Stage
    29.5 discovery module; verifier = models + the committed Stage 30.14.0 orchestrator +
    replay source);
  * the EXPLICIT, SCOPED Stage 29.5 deviation; NO Birdeye / Stage 27 / Stage 28 / Stage
    29.1-29.4 import;
  * NO durable-ledger / real-send-guard / Discord / Telegram / Stage 28 / Yellowstone /
    Chainstack / dispatcher import;
  * no ``os.environ`` / ``os.getenv`` access;
  * no database / compression / network / concurrency / clock import;
  * no Stage 21-28 / PHX1 import;
  * no forbidden secret / transport / URL text needle and no ``://`` literal;
  * NO filesystem WRITE surface in any module; the strict tier carries no filesystem surface
    at all;
  * no implicit I/O at import time (zero top-level Call nodes);
  * no unbounded ``while`` loop / daemon / thread surface;
  * the inventory admits no Stage 31 file.

Fake / offline / no-send only.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_14_1_manifest import (
    STAGE30_14_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_14_1_ALLOWED_STAGE29_IMPORTS,
    STAGE30_14_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_14_1_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_14_1_FORBIDDEN_WRITE_SURFACES,
    STAGE30_14_1_LOADER_ALLOWED_PHX2_IMPORTS,
    STAGE30_14_1_LOADER_ALLOWED_STDLIB_IMPORTS,
    STAGE30_14_1_LOADER_BASENAME,
    STAGE30_14_1_LOADER_SCANNED_BASENAMES,
    STAGE30_14_1_MODELS_ALLOWED_PHX2_IMPORTS,
    STAGE30_14_1_MODELS_BASENAME,
    STAGE30_14_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_14_1_STAGE29_MIGRATION_MODELS_MODULE,
    STAGE30_14_1_STAGE30_14_0_ORCHESTRATOR_MODULE,
    STAGE30_14_1_STAGE30_14_0_REPLAY_SOURCE_MODULE,
    STAGE30_14_1_STRICT_ALLOWED_STDLIB_IMPORTS,
    STAGE30_14_1_STRICT_SCANNED_BASENAMES,
    STAGE30_14_1_TEST_BASENAMES,
    STAGE30_14_1_VERIFIER_ALLOWED_PHX2_IMPORTS,
    STAGE30_14_1_VERIFIER_BASENAME,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_14_1_SCANNED_PRODUCTION_BASENAMES
    }


def _module_ast(text: str) -> ast.Module:
    return ast.parse(text)


def _imports_of(text: str) -> Set[str]:
    modules: Set[str] = set()
    for node in ast.walk(_module_ast(text)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def _phx2_imports_of(basename: str) -> Set[str]:
    return {
        m for m in _imports_of(_source_of(basename)) if m.startswith("PHX2.")
    }


def _stdlib_allowlist_for(basename: str) -> Tuple[str, ...]:
    if basename in STAGE30_14_1_LOADER_SCANNED_BASENAMES:
        return STAGE30_14_1_LOADER_ALLOWED_STDLIB_IMPORTS
    return STAGE30_14_1_STRICT_ALLOWED_STDLIB_IMPORTS


def _phx2_allowlist_for(basename: str) -> Tuple[str, ...]:
    if basename == STAGE30_14_1_MODELS_BASENAME:
        return STAGE30_14_1_MODELS_ALLOWED_PHX2_IMPORTS
    if basename == STAGE30_14_1_LOADER_BASENAME:
        return STAGE30_14_1_LOADER_ALLOWED_PHX2_IMPORTS
    if basename == STAGE30_14_1_VERIFIER_BASENAME:
        return STAGE30_14_1_VERIFIER_ALLOWED_PHX2_IMPORTS
    raise AssertionError(f"unexpected scanned basename {basename!r}")


# ---------------------------------------------------------------------------
# 1. Files exist + scanned set is a subset of the inventory + import cleanly
# ---------------------------------------------------------------------------


def test_inventory_files_exist() -> None:
    for basename in STAGE30_14_1_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.14.1 requires {basename}"
        )


def test_scanned_basenames_subset_of_inventory() -> None:
    for basename in STAGE30_14_1_SCANNED_PRODUCTION_BASENAMES:
        assert basename in STAGE30_14_1_ALLOWED_STAGE30_BASENAMES
        assert (STAGE30_ROOT / basename).is_file()
    # The two tiers partition the scanned set.
    assert set(STAGE30_14_1_STRICT_SCANNED_BASENAMES).isdisjoint(
        set(STAGE30_14_1_LOADER_SCANNED_BASENAMES)
    )
    assert set(STAGE30_14_1_SCANNED_PRODUCTION_BASENAMES) == (
        set(STAGE30_14_1_STRICT_SCANNED_BASENAMES)
        | set(STAGE30_14_1_LOADER_SCANNED_BASENAMES)
    )


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_14_1_evidence_artifact_models  # noqa: F401
    import PHX2.stage30.stage30_14_1_evidence_artifact_loader  # noqa: F401
    import PHX2.stage30.stage30_14_1_replay_verifier  # noqa: F401
    import PHX2.stage30.stage30_14_1_manifest  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Two-tier stdlib import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_imports_within_per_tier_allowlist() -> None:
    for basename, text in _scanned_sources().items():
        allowlist = _stdlib_allowlist_for(basename)
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            top = module.split(".")[0]
            assert module in allowlist or top in allowlist, (
                f"Stage 30.14.1 module {basename!r} imports non-allowlisted "
                f"stdlib module {module!r} for its tier"
            )


def test_strict_tier_excludes_json_pathlib_and_loader_tier_includes_them() -> None:
    assert "json" not in STAGE30_14_1_STRICT_ALLOWED_STDLIB_IMPORTS
    assert "pathlib" not in STAGE30_14_1_STRICT_ALLOWED_STDLIB_IMPORTS
    assert "json" in STAGE30_14_1_LOADER_ALLOWED_STDLIB_IMPORTS
    assert "pathlib" in STAGE30_14_1_LOADER_ALLOWED_STDLIB_IMPORTS


def test_both_tiers_exclude_io_db_and_clock() -> None:
    for allowlist in (
        STAGE30_14_1_STRICT_ALLOWED_STDLIB_IMPORTS,
        STAGE30_14_1_LOADER_ALLOWED_STDLIB_IMPORTS,
    ):
        for forbidden in ("os", "datetime", "time", "decimal", "re", "sqlite3"):
            assert forbidden not in allowlist


# ---------------------------------------------------------------------------
# 3. Per-module + combined PHX2 import allowlists
# ---------------------------------------------------------------------------


def test_phx2_imports_within_per_module_allowlist() -> None:
    for basename in STAGE30_14_1_SCANNED_PRODUCTION_BASENAMES:
        allowed = set(_phx2_allowlist_for(basename))
        for module in _phx2_imports_of(basename):
            assert module in allowed, (
                f"Stage 30.14.1 module {basename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )
            assert module in STAGE30_14_1_ALLOWED_PHX2_IMPORTS


def test_models_leaf_imports_no_phx2() -> None:
    assert _phx2_imports_of(STAGE30_14_1_MODELS_BASENAME) == set()


def test_loader_composes_models_and_discovery_currency() -> None:
    phx2 = _phx2_imports_of(STAGE30_14_1_LOADER_BASENAME)
    assert STAGE30_14_1_STAGE29_MIGRATION_MODELS_MODULE in phx2
    assert any(m.endswith("evidence_artifact_models") for m in phx2)


def test_verifier_composes_committed_stage30_14_0() -> None:
    phx2 = _phx2_imports_of(STAGE30_14_1_VERIFIER_BASENAME)
    assert STAGE30_14_1_STAGE30_14_0_ORCHESTRATOR_MODULE in phx2
    assert STAGE30_14_1_STAGE30_14_0_REPLAY_SOURCE_MODULE in phx2
    # The verifier does NOT import the loader (filesystem stays in the loader tier).
    assert not any(m.endswith("evidence_artifact_loader") for m in phx2)


# ---------------------------------------------------------------------------
# 4. Scoped Stage 29.5 deviation; no other provider / cross-stage surface
# ---------------------------------------------------------------------------


def test_stage29_allowlist_is_exactly_the_one_discovery_module() -> None:
    assert set(STAGE30_14_1_ALLOWED_STAGE29_IMPORTS) == {
        STAGE30_14_1_STAGE29_MIGRATION_MODELS_MODULE,
    }


def test_every_stage29_import_is_the_discovery_currency_module() -> None:
    for basename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2.stage29"):
                assert module in STAGE30_14_1_ALLOWED_STAGE29_IMPORTS, (
                    f"Stage 30.14.1 module {basename!r} imports non-discovery "
                    f"Stage 29 module {module!r}"
                )


def test_no_birdeye_or_stage27_28_or_non_discovery_stage29() -> None:
    for basename, text in _scanned_sources().items():
        for module in _imports_of(text):
            assert "birdeye" not in module.lower()
            assert "stage27" not in module
            assert "stage28" not in module
            for nope in ("stage29_1", "stage29_2", "stage29_3", "stage29_4"):
                assert nope not in module


_FORBIDDEN_SEND_OR_LEDGER_SUBSTRINGS = (
    "stage30_11_15",  # durable / in-memory ping_dedupe ledger module
    "stage30_11_16",  # real-send guard
    "discord",
    "telegram",
    "yellowstone",
    "chainstack",
    "dispatcher",
)


def test_no_durable_ledger_or_real_send_or_routing_imports() -> None:
    for basename, text in _scanned_sources().items():
        for module in _imports_of(text):
            lowered = module.lower()
            for forbidden in _FORBIDDEN_SEND_OR_LEDGER_SUBSTRINGS:
                assert forbidden not in lowered, (
                    f"Stage 30.14.1 module {basename!r} imports a forbidden "
                    f"send / durable-ledger / routing module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No env / db / network / clock / stage21-28 / PHX1 imports
# ---------------------------------------------------------------------------


def test_no_environ_access() -> None:
    for basename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.14.1 module {basename!r} performs os.{node.attr}"
                )


_FORBIDDEN_DB_OR_COMPRESSION_MODULES = (
    "sqlite3",
    "dbm",
    "zstandard",
    "zstd",
    "lzma",
    "gzip",
    "zlib",
    "bz2",
    "shutil",
    "pickle",
    "marshal",
)


def test_no_db_or_compression_surface_imports() -> None:
    for basename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_DB_OR_COMPRESSION_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.14.1 module {basename!r} imports db / "
                    f"compression surface {module!r}"
                )


# ``json`` + ``pathlib`` are DELIBERATELY admitted in the loader tier and are NOT in this
# forbidden list; everything network / concurrency / clock is.
_FORBIDDEN_NETWORK_OR_CONCURRENCY_MODULES = (
    "urllib",
    "socket",
    "grpc",
    "asyncio",
    "aiohttp",
    "httpx",
    "requests",
    "websockets",
    "websocket",
    "http",
    "ssl",
    "dotenv",
    "keyring",
    "subprocess",
    "threading",
    "multiprocessing",
    "concurrent",
    "signal",
    "time",
    "sched",
    "random",
    "datetime",
    "re",
)


def test_no_network_concurrency_or_clock_module_imports() -> None:
    for basename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_OR_CONCURRENCY_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.14.1 module {basename!r} imports forbidden "
                    f"network / concurrency / clock module {module!r}"
                )


def test_no_stage21_28_or_phx1_imports() -> None:
    for basename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for stage_n in range(21, 29):  # 21..28 (Stage 29.5 discovery is allowed)
                prefix = f"PHX2.stage{stage_n}"
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.14.1 module {basename!r} imports Stage 21-28 "
                    f"module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.14.1 module {basename!r} imports PHX1 {module!r}"
            )


# ---------------------------------------------------------------------------
# 6. No forbidden secret / transport / URL needles + no scheme literal
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for basename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_14_1_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.14.1 module {basename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for basename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.14.1 module {basename!r} carries a transport scheme "
            "literal"
        )


# ---------------------------------------------------------------------------
# 7. Filesystem: no WRITE surface anywhere; strict tier has no fs surface
# ---------------------------------------------------------------------------


def test_no_filesystem_write_surface() -> None:
    for basename, text in _scanned_sources().items():
        for needle in STAGE30_14_1_FORBIDDEN_WRITE_SURFACES:
            assert needle not in text, (
                f"Stage 30.14.1 module {basename!r} carries a filesystem "
                f"WRITE surface {needle!r}"
            )


def test_strict_tier_carries_no_filesystem_surface() -> None:
    fs_needles = ("Path(", ".read_text(", ".read_bytes(", "open(", ".stat(")
    for basename in STAGE30_14_1_STRICT_SCANNED_BASENAMES:
        text = _source_of(basename)
        for needle in fs_needles:
            assert needle not in text, (
                f"Stage 30.14.1 strict module {basename!r} carries a "
                f"filesystem surface {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. No implicit I/O at import + no unbounded loop / daemon / thread
# ---------------------------------------------------------------------------


def _top_level_call_values(tree: ast.Module):
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            yield stmt.value
        elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            yield stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(
            stmt.value, ast.Call
        ):
            yield stmt.value


def test_no_top_level_call_nodes() -> None:
    for basename, text in _scanned_sources().items():
        calls = list(_top_level_call_values(_module_ast(text)))
        assert calls == [], (
            f"Stage 30.14.1 module {basename!r} carries a top-level call "
            "(implicit I/O at import time)"
        )


def test_no_while_loop_in_any_production_module() -> None:
    for basename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.14.1 module {basename!r} carries a while loop"
            )


def _called_names(text: str) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(_module_ast(text)):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def test_no_daemon_or_thread_surface() -> None:
    needles = ("daemon", "thread", "spawn", "fork", "sleep")
    for basename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.14.1 module {basename!r} calls a daemon / "
                    f"thread surface {name!r}"
                )


# ---------------------------------------------------------------------------
# 9. Inventory admits no Stage 31 file
# ---------------------------------------------------------------------------


_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_14_1_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_14_1_TEST_BASENAMES)
    )
    for basename in inventory:
        assert _STAGE_31_RE.search(basename.lower()) is None, (
            f"Stage 30.14.1 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )
