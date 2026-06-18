"""Stage 30.14 real-discovery-replay -> shadow-dispatch boundary tests.

Scans the Stage 30.14 scanned production modules (data-driven from the manifest's
``STAGE30_14_SCANNED_PRODUCTION_BASENAMES``) for:

  * a positive stdlib import allowlist (``__future__`` / ``typing`` / ``dataclasses``
    ONLY -- no decimal / datetime / re / os / network);
  * a positive PHX2 import allowlist (the own Stage 30.14 siblings + the one committed Stage
    29.5 discovery-currency module + the committed Stage 30.13.0 auto-seeder + the committed
    Stage 30.11.23 fake proof);
  * the EXPLICIT, SCOPED Stage 29.5 deviation: every Stage 29 import is the one
    discovery-currency migration-models module; NO Birdeye / Stage 27 / Stage 28 / Stage
    29.1-29.4 import;
  * the models module is a pure leaf (no PHX2 import);
  * the orchestrator composes the committed auto-seeder + the committed Stage 30.11.23 fake
    proof; the replay source composes the committed Stage 29.5 migration models;
  * NO durable-ledger / real-send-guard / Discord / Telegram / Stage 28 / Yellowstone /
    Chainstack import (the no-send / no-durable-ledger boundary);
  * no ``os.environ`` / ``os.getenv`` access;
  * no database / SQLite / compression surface import;
  * no network / concurrency / clock import;
  * no Stage 21-28 / PHX1 import;
  * no forbidden secret / transport / URL text needle and no ``://`` literal;
  * no filesystem-write surface;
  * no implicit I/O at import time (zero top-level Call nodes);
  * no unbounded ``while`` loop / daemon / thread surface;
  * the Stage 30.14 inventory admits no Stage 31 file.

Fake / offline / no-send only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set

from PHX2.stage30.stage30_14_manifest import (
    STAGE30_14_0_MODELS_BASENAME,
    STAGE30_14_0_ORCHESTRATOR_BASENAME,
    STAGE30_14_0_REPLAY_SOURCE_BASENAME,
    STAGE30_14_ALLOWED_PHX2_IMPORTS,
    STAGE30_14_ALLOWED_STAGE29_IMPORTS,
    STAGE30_14_ALLOWED_STAGE30_BASENAMES,
    STAGE30_14_ALLOWED_STDLIB_IMPORTS,
    STAGE30_14_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_14_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE,
    STAGE30_14_STAGE30_11_23_FAKE_PROOF_MODULE,
    STAGE30_14_STAGE30_13_0_AUTO_SEEDER_MODULE,
    STAGE30_14_TEST_BASENAMES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_14_SCANNED_PRODUCTION_BASENAMES
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


# ---------------------------------------------------------------------------
# 1. Files exist + scanned set is a subset of the inventory + import cleanly
# ---------------------------------------------------------------------------


def test_inventory_files_exist() -> None:
    for basename in STAGE30_14_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.14 requires {basename}"
        )


def test_scanned_basenames_subset_of_inventory_and_exist() -> None:
    for basename in STAGE30_14_SCANNED_PRODUCTION_BASENAMES:
        assert basename in STAGE30_14_ALLOWED_STAGE30_BASENAMES
        assert (STAGE30_ROOT / basename).is_file()


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_14_0_replay_discovery_models  # noqa: F401
    import PHX2.stage30.stage30_14_0_replay_discovery_source  # noqa: F401
    import PHX2.stage30.stage30_14_0_real_discovery_to_shadow_dispatch  # noqa: F401,E501
    import PHX2.stage30.stage30_14_manifest  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Positive stdlib + PHX2 import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_in_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            top = module.split(".")[0]
            assert (
                module in STAGE30_14_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_14_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.14 module {filename!r} imports non-allowlisted stdlib "
                f"module {module!r}"
            )


def test_stdlib_allowlist_excludes_io_db_and_clock() -> None:
    for forbidden in (
        "os",
        "json",
        "pathlib",
        "datetime",
        "decimal",
        "re",
        "sqlite3",
        "time",
    ):
        assert forbidden not in STAGE30_14_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_14_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.14 module {filename!r} imports non-allowlisted PHX2 "
                f"module {module!r}"
            )


# ---------------------------------------------------------------------------
# 3. The scoped Stage 29.5 discovery-currency deviation
# ---------------------------------------------------------------------------


def test_stage29_allowlist_is_exactly_the_one_discovery_module() -> None:
    assert set(STAGE30_14_ALLOWED_STAGE29_IMPORTS) == {
        STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE,
    }


def test_every_stage29_import_is_the_discovery_currency_module() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2.stage29"):
                assert module in STAGE30_14_ALLOWED_STAGE29_IMPORTS, (
                    f"Stage 30.14 module {filename!r} imports non-discovery Stage 29 "
                    f"module {module!r}"
                )


def test_no_birdeye_or_other_provider_or_stage27_28() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            assert "birdeye" not in module.lower(), (
                f"Stage 30.14 module {filename!r} imports a provider module {module!r}"
            )
            assert "stage27" not in module, (
                f"Stage 30.14 module {filename!r} imports a Stage 27 module {module!r}"
            )
            assert "stage28" not in module, (
                f"Stage 30.14 module {filename!r} imports a Stage 28 module {module!r}"
            )
            for nope in ("stage29_1", "stage29_2", "stage29_3", "stage29_4"):
                assert nope not in module, (
                    f"Stage 30.14 module {filename!r} imports a non-discovery Stage 29 "
                    f"module {module!r}"
                )


def test_models_module_imports_no_phx2() -> None:
    assert _phx2_imports_of(STAGE30_14_0_MODELS_BASENAME) == set()


def test_replay_source_composes_committed_discovery_currency() -> None:
    phx2 = _phx2_imports_of(STAGE30_14_0_REPLAY_SOURCE_BASENAME)
    assert STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE in phx2, (
        "the replay source must read the committed Stage 29.5 closed-set capture error"
    )


def test_orchestrator_composes_committed_seeder_and_recheck_chain() -> None:
    phx2 = _phx2_imports_of(STAGE30_14_0_ORCHESTRATOR_BASENAME)
    assert STAGE30_14_STAGE30_13_0_AUTO_SEEDER_MODULE in phx2, (
        "the orchestrator must drive the committed Stage 30.13.0 auto-seeder"
    )
    assert STAGE30_14_STAGE30_11_23_FAKE_PROOF_MODULE in phx2, (
        "the orchestrator must feed the committed Stage 30.11.23 fake real-fed proof"
    )


# ---------------------------------------------------------------------------
# 4. No durable-ledger / real-send-guard / Discord / Stage 28 / gRPC surface
# ---------------------------------------------------------------------------


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
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            lowered = module.lower()
            for forbidden in _FORBIDDEN_SEND_OR_LEDGER_SUBSTRINGS:
                assert forbidden not in lowered, (
                    f"Stage 30.14 module {filename!r} imports a forbidden send / "
                    f"durable-ledger / routing module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No env / db / network / clock / stage21-28 / PHX1 imports
# ---------------------------------------------------------------------------


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.14 module {filename!r} performs os.{node.attr} access"
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
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_DB_OR_COMPRESSION_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.14 module {filename!r} imports database / compression "
                    f"surface {module!r}"
                )


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
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_OR_CONCURRENCY_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.14 module {filename!r} imports forbidden network / "
                    f"concurrency / clock module {module!r}"
                )


def test_no_stage21_28_or_phx1_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for stage_n in range(21, 29):  # 21..28 (Stage 29.5 discovery is allowed)
                prefix = f"PHX2.stage{stage_n}"
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.14 module {filename!r} imports Stage 21-28 module "
                    f"{module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.14 module {filename!r} imports PHX1 {module!r}"
            )


# ---------------------------------------------------------------------------
# 6. No forbidden secret / transport / URL needles + no scheme literal
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_14_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.14 module {filename!r} carries forbidden text needle "
                f"{needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.14 module {filename!r} carries a transport scheme literal"
        )


# ---------------------------------------------------------------------------
# 7. No filesystem-write surface
# ---------------------------------------------------------------------------


_FS_WRITE_NEEDLES = (
    "open(",
    "Path(",
    ".write_text(",
    ".write_bytes(",
    ".mkdir(",
)


def test_no_filesystem_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in _FS_WRITE_NEEDLES:
            assert needle not in text, (
                f"Stage 30.14 module {filename!r} carries a filesystem surface "
                f"{needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. No implicit I/O at import time + no unbounded loop / daemon / thread
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
    for filename, text in _scanned_sources().items():
        calls = list(_top_level_call_values(_module_ast(text)))
        assert calls == [], (
            f"Stage 30.14 module {filename!r} carries a top-level call "
            f"(implicit I/O at import time)"
        )


def test_no_while_loop_in_any_production_module() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.14 module {filename!r} carries a while loop"
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
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.14 module {filename!r} calls a daemon / thread surface "
                    f"{name!r}"
                )


# ---------------------------------------------------------------------------
# 9. Inventory admits no Stage 31 file
# ---------------------------------------------------------------------------


_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_14_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_14_TEST_BASENAMES)
    )
    for basename in inventory:
        assert _STAGE_31_RE.search(basename.lower()) is None, (
            f"Stage 30.14 inventory must carry no Stage 31 token; offender {basename!r}"
        )
