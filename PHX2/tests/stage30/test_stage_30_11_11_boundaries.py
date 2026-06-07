"""Stage 30.11.11 migration-anchored ATH source boundary tests.

Scans the ONE Stage 30.11.11 production module (the migration-anchored ATH
source) for:

  * a positive stdlib import allowlist (``__future__`` / ``typing`` /
    ``dataclasses`` / ``datetime`` -- ``datetime`` parses the caller anchor + the
    injected ``now``; NO ``decimal`` / ``re`` / ``os`` / ``json`` / ``sqlite3``),
  * a positive PHX2 import allowlist -- the committed Stage 27.4 reader /
    contracts / models / migration / ingest / pair-detection siblings + the
    committed Stage 29.2 anchored ATH fetch / price source / models / constants.
    This is the DELIBERATE, audited Stage 30.11.11 import expansion: the source
    IS the committed real ATH context source, so (unlike the leaf Stage 30.11.10
    resolver) it composes Stage 27.4 + Stage 29.2 directly (read-only). It proves,
    by construction, that it imports NO Stage 28 / Stage 21-26 / other Stage 30
    (no Stage 30.12 renderer / display, no Stage 30.11.5 runner / transport, no
    Stage 30.11.10 resolver) / PHX1 / network-transport / Discord module,
  * no ``os`` import / ``os.environ`` access; no network / db / compression /
    concurrency import; no forbidden secret / transport / URL needle (the Stage
    30.11.11 needle set -- the family set minus the ``endpoint_secret`` KEYWORD
    the source legitimately forwards to the committed Stage 29.2 ctors); no
    ``://`` scheme; no real send call; no filesystem write; no ``datetime.now`` /
    ``utcnow`` / ``today`` call (the clock is injected); no while loop / daemon;
    no implicit I/O at import time; and the slice is a leaf (no OTHER stage30
    file imports it).

Fake / offline only. No live call, no provider, no private send, no env read.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_11_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_11_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_11_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_11_ANCHORED_ATH_SOURCE_BASENAME,
    STAGE30_11_11_ANCHORED_ATH_SOURCE_MODULE,
    STAGE30_11_11_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_11_11_SCANNED_PRODUCTION_BASENAMES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_11_11_SCANNED_PRODUCTION_BASENAMES
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


# ---------------------------------------------------------------------------
# 1. File exists + imports cleanly + scanned set is the one module
# ---------------------------------------------------------------------------


def test_production_file_exists() -> None:
    for basename in STAGE30_11_11_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file()


def test_scanned_basename_is_the_one_module() -> None:
    assert STAGE30_11_11_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_11_ALLOWED_STAGE30_BASENAMES
    )
    assert STAGE30_11_11_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_11_ANCHORED_ATH_SOURCE_BASENAME,
    )


def test_module_imports_cleanly() -> None:
    import PHX2.stage30.stage30_11_11_migration_anchored_ath_source  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Positive stdlib + PHX2 import allowlists
# ---------------------------------------------------------------------------


def test_non_phx2_imports_are_in_stdlib_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            top = module.split(".")[0]
            assert (
                module in STAGE30_11_11_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_11_11_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.11.11 module {filename!r} imports non-allowlisted "
                f"stdlib / third-party module {module!r}"
            )


def test_stdlib_allowlist_excludes_decimal_re_os_db_surfaces() -> None:
    for forbidden in (
        "decimal",
        "re",
        "os",
        "json",
        "pathlib",
        "sqlite3",
        "zstandard",
        "asyncio",
        "threading",
    ):
        assert forbidden not in STAGE30_11_11_ALLOWED_STDLIB_IMPORTS
    # datetime IS allowed (it parses the anchor + the injected now).
    assert "datetime" in STAGE30_11_11_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_11_11_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.11.11 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_exactly_stage27_4_and_stage29_2() -> None:
    expected = (
        "PHX2.stage27.price_ath_context_contracts",
        "PHX2.stage27.price_ath_context_models",
        "PHX2.stage27.price_ath_context_reader",
        "PHX2.stage27.migration_context_models",
        "PHX2.stage27.provider_ingest_models",
        "PHX2.stage27.pair_detection_constants",
        "PHX2.stage29.birdeye_constants",
        "PHX2.stage29.stage29_2_birdeye_ath_source",
        "PHX2.stage29.stage29_2_birdeye_models",
        "PHX2.stage29.stage29_2_birdeye_price_source",
    )
    assert STAGE30_11_11_ALLOWED_PHX2_IMPORTS == expected
    for module in STAGE30_11_11_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage27.") or module.startswith(
            "PHX2.stage29."
        )


def test_no_other_stage30_or_stage28_or_phx1_import() -> None:
    # The audited expansion admits Stage 27.4 + Stage 29.2 ONLY. It must import
    # NO Stage 28, NO Stage 21-26, NO other Stage 30 (no renderer / runner /
    # resolver), and NO PHX1.
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            assert not module.startswith("PHX2.stage30."), (
                f"{filename!r} imports a Stage 30 module {module!r} (the source "
                f"composes only Stage 27.4 + Stage 29.2)"
            )
            assert not module.startswith("PHX2.stage28"), (
                f"{filename!r} imports a Stage 28 module {module!r}"
            )
            for stage_n in range(21, 27):
                assert not module.startswith(f"PHX2.stage{stage_n}"), (
                    f"{filename!r} imports a Stage 21-26 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"{filename!r} imports a PHX1 module {module!r}"
            )


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports
        for module in imports:
            assert not module.startswith("os.")


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.11.11 module {filename!r} performs os.{node.attr}"
                )


# ---------------------------------------------------------------------------
# 4. No network / db / compression / concurrency import (datetime IS allowed)
# ---------------------------------------------------------------------------


_FORBIDDEN_MODULES: Tuple[str, ...] = (
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
    "decimal",
    "re",
)


def test_no_network_db_concurrency_or_decimal_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.11.11 module {filename!r} imports forbidden "
                    f"module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No Discord / provider-transport / runner import surface (skip allowlist)
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_NEEDLES: Tuple[str, ...] = (
    "discord",
    "telegram",
    "web" + "hook",
    "renderer",
    "live_provider",
    "suppress",
    "orchestrator",
    "transport",
    "runner",
)


def test_no_discord_runner_or_transport_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module in STAGE30_11_11_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.11.11 module {filename!r} imports forbidden "
                    f"surface {needle!r}; offender {module!r}"
                )


# ---------------------------------------------------------------------------
# 6. No forbidden secret / transport / URL text needles + no scheme literal
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_11_11_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.11.11 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_needle_set_omits_only_endpoint_secret_vs_family() -> None:
    # The Stage 30.11.11 needle set is the family set MINUS the
    # ``endpoint`` + ``_secret`` needle (the committed Stage 29.2 keyword the
    # source forwards). Every other family needle is retained.
    from PHX2.stage30.stage30_11_manifest import (
        STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
    )

    family = set(STAGE30_11_FORBIDDEN_TEXT_NEEDLES)
    own = set(STAGE30_11_11_FORBIDDEN_TEXT_NEEDLES)
    assert family - own == {"endpoint" + "_secret"}
    # The genuinely-forbidden URL / secret needles are all retained.
    for needle in (
        "discord" + ".com",
        "h" + "ttps://",
        "api_" + "key",
        "b" + "earer",
        "x-api-" + "key",
        "hel" + "ius",
        "chain" + "stack",
    ):
        assert needle in own


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text


# ---------------------------------------------------------------------------
# 7. No real send call; no filesystem write
# ---------------------------------------------------------------------------


def test_calls_no_real_send_surface() -> None:
    forbidden = ("discord", "web" + "hook", "urlopen", "send_one_audited_post")
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for bad in forbidden:
                assert bad not in lowered, (
                    f"Stage 30.11.11 module {filename!r} calls a real send "
                    f"surface {name!r}"
                )


def test_no_filesystem_write_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in ("open(", ".write_text(", ".write_bytes(", "Path("):
            assert needle not in text, (
                f"Stage 30.11.11 module {filename!r} carries a filesystem write "
                f"surface {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. Determinism: the clock is injected (no datetime.now / utcnow / today call)
# ---------------------------------------------------------------------------


def test_no_wall_clock_read_call() -> None:
    for filename, text in _scanned_sources().items():
        called = _called_names(text)
        for forbidden in ("now", "utcnow", "today"):
            assert forbidden not in called, (
                f"Stage 30.11.11 module {filename!r} calls datetime.{forbidden} "
                f"(the clock must be injected)"
            )


# ---------------------------------------------------------------------------
# 9. No unbounded loop / daemon / thread
# ---------------------------------------------------------------------------


def test_no_while_loop() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.11.11 module {filename!r} carries a while loop"
            )


def test_no_daemon_or_thread_surface() -> None:
    needles = ("daemon", "thread", "spawn", "fork", "sleep")
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.11.11 module {filename!r} calls daemon/thread "
                    f"surface {name!r}"
                )


# ---------------------------------------------------------------------------
# 10. No implicit I/O at import time (zero top-level Call nodes)
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
            f"Stage 30.11.11 module {filename!r} carries a top-level call "
            f"(implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# 11. The slice is a LEAF: no existing stage30 file imports it
# ---------------------------------------------------------------------------


def test_no_existing_stage30_file_imports_the_slice() -> None:
    own = set(STAGE30_11_11_ALLOWED_STAGE30_BASENAMES)
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__" or not entry.name.endswith(".py"):
            continue
        if entry.name in own:
            continue
        text = entry.read_text(encoding="utf-8")
        for module in _imports_of(text):
            assert module != STAGE30_11_11_ANCHORED_ATH_SOURCE_MODULE, (
                f"{entry.name!r} imports the Stage 30.11.11 slice; it is a leaf "
                f"and is not wired into the in-repo runtime"
            )
