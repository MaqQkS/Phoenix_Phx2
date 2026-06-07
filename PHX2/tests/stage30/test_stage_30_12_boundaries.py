"""Stage 30.12 PHOENIX operator ping renderer boundary tests.

Scans the two Stage 30.12 non-manifest production .py modules (the renderer
models + the renderer) for (the constants-only manifest is validated separately
by the Stage 30.12 manifest test):

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` / ``re``
    / ``decimal`` -- ``re`` + ``decimal`` ARE allowed: the renderer validates
    safe shapes and formats clean prices),
  * a positive PHX2 import allowlist (the renderer imports ONLY the models
    sibling; the models + manifest import no PHX2 module) -- proving the slice
    is a clean LEAF that imports no Stage 21-29 / Stage 30.1 / Stage 30.2 /
    Stage 30.11 / runtime orchestrator / renderer-runtime / transport / Discord
    / live-provider / network module,
  * no ``os`` import / ``os.environ`` access; no db / compression / network /
    clock / concurrency import; no Stage 21-29 / PHX1 import; no forbidden
    URL / secret / transport text needle; no transport-scheme literal; no
    public / social / trading / wallet / enforcement term; no real send call;
    no filesystem write; no unbounded loop / daemon; and the slice is a leaf
    (no OTHER stage30 file imports it).

Pure / offline only. No live call, no provider, no private send, no env read.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_12_manifest import (
    STAGE30_12_1_BODY_BUILDER_BASENAME,
    STAGE30_12_ALLOWED_PHX2_IMPORTS,
    STAGE30_12_ALLOWED_STAGE30_BASENAMES,
    STAGE30_12_ALLOWED_STDLIB_IMPORTS,
    STAGE30_12_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_12_MANIFEST_BASENAME,
    STAGE30_12_MODELS_BASENAME,
    STAGE30_12_MODELS_MODULE,
    STAGE30_12_RENDERER_BASENAME,
    STAGE30_12_RENDERER_MODULE,
    STAGE30_12_SCANNED_PRODUCTION_BASENAMES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_12_SCANNED_PRODUCTION_BASENAMES
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
# 1. Files exist + import cleanly + scanned set is the three modules
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_12_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.12 requires {basename}"
        )


def test_scanned_basenames_are_the_three_non_manifest_modules() -> None:
    assert STAGE30_12_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_12_MODELS_BASENAME,
        STAGE30_12_RENDERER_BASENAME,
        STAGE30_12_1_BODY_BUILDER_BASENAME,
    )
    assert len(STAGE30_12_SCANNED_PRODUCTION_BASENAMES) == 3
    assert STAGE30_12_MANIFEST_BASENAME not in (
        STAGE30_12_SCANNED_PRODUCTION_BASENAMES
    )


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_12_phoenix_operator_ping_models  # noqa: F401
    import PHX2.stage30.stage30_12_phoenix_operator_ping_renderer  # noqa: F401
    import PHX2.stage30.stage30_12_manifest  # noqa: F401
    import PHX2.stage30.stage30_12_1_phoenix_operator_ping_body_builder  # noqa: F401,E501


# ---------------------------------------------------------------------------
# 2. Positive stdlib + PHX2 import allowlists (the slice is a LEAF)
# ---------------------------------------------------------------------------


def test_non_phx2_imports_are_in_stdlib_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            top = module.split(".")[0]
            assert (
                module in STAGE30_12_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_12_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.12 module {filename!r} imports non-allowlisted "
                f"stdlib / third-party module {module!r}"
            )


def test_stdlib_allowlist_excludes_io_db_clock_and_network_surfaces() -> None:
    for forbidden in (
        "os",
        "json",
        "pathlib",
        "sqlite3",
        "zstandard",
        "time",
        "datetime",
        "asyncio",
        "threading",
        "socket",
        "urllib",
    ):
        assert forbidden not in STAGE30_12_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_12_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.12 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_exactly_the_two_own_siblings() -> None:
    assert STAGE30_12_ALLOWED_PHX2_IMPORTS == (
        STAGE30_12_MODELS_MODULE,
        STAGE30_12_RENDERER_MODULE,
    )


def test_models_and_manifest_import_no_phx2_module() -> None:
    assert _phx2_imports_of(STAGE30_12_MODELS_BASENAME) == set()
    assert _phx2_imports_of(STAGE30_12_MANIFEST_BASENAME) == set()


def test_renderer_imports_only_the_models_sibling() -> None:
    assert _phx2_imports_of(STAGE30_12_RENDERER_BASENAME) == {
        STAGE30_12_MODELS_MODULE
    }


def test_no_broad_prefix_allowlist() -> None:
    for module in STAGE30_12_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_12_")
        assert not module.endswith(".")
        assert "*" not in module
    for prefix in ("PHX2", "PHX2.stage30", "PHX2.stage30.stage30_12_"):
        assert prefix not in STAGE30_12_ALLOWED_PHX2_IMPORTS


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.12 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.12 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.12 module {filename!r} performs "
                    f"os.{node.attr} access"
                )


# ---------------------------------------------------------------------------
# 4. No database / compression / network / clock / concurrency imports
#    (``re`` + ``decimal`` ARE allowed and are NOT in this forbidden set)
# ---------------------------------------------------------------------------


_FORBIDDEN_MODULES: Tuple[str, ...] = (
    "os",
    "io",
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
    "datetime",
    "sched",
    "random",
)


def test_no_forbidden_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.12 module {filename!r} imports forbidden "
                    f"module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / PHX1 import (and no Stage 30.1 / 30.2 / 30.11 import)
# ---------------------------------------------------------------------------


def test_no_stage21_29_or_phx1_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for stage_n in range(21, 30):
                forbidden_prefix = f"PHX2.stage{stage_n}"
                assert not (
                    module == forbidden_prefix
                    or module.startswith(forbidden_prefix + ".")
                ), (
                    f"Stage 30.12 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.12 module {filename!r} imports PHX1 module "
                f"{module!r}"
            )


def test_no_other_stage30_family_import() -> None:
    # The slice composes only its own two siblings; it must not import the Stage
    # 30.1 tier model, the Stage 30.2 compact renderer, or any Stage 30.11
    # runner / gate / transport module.
    allowed = set(STAGE30_12_ALLOWED_PHX2_IMPORTS)
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2.stage30."):
                continue
            assert module in allowed, (
                f"Stage 30.12 module {filename!r} imports a non-own stage30 "
                f"module {module!r}"
            )


# ---------------------------------------------------------------------------
# 6. No Discord / provider / runtime / transport import surface
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_NEEDLES: Tuple[str, ...] = (
    "discord",
    "telegram",
    "birdeye",
    "hel" + "ius",
    "chain" + "stack",
    "pump",
    "solders",
    "solana",
    "web" + "hook",
    "dex" + "screener",
    "orchestrator",
    "transport",
    "live_provider",
    "suppress",
)


def test_no_provider_runtime_or_transport_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module in STAGE30_12_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.12 module {filename!r} imports forbidden "
                    f"surface {needle!r}; offender {module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden URL / secret / transport text needles + no transport scheme
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_12_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.12 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    scheme = ":" + "/" + "/"
    for filename, text in _scanned_sources().items():
        assert scheme not in text, (
            f"Stage 30.12 module {filename!r} carries a transport scheme "
            f"literal"
        )


# ---------------------------------------------------------------------------
# 8. No public / subscriber / paid / social / trading / wallet / enforcement
# ---------------------------------------------------------------------------


# Operational multi-word phrases that must never appear in the renderer's
# source. Single provider / social WORDS (Discord / Telegram / Helius / ...) are
# intentionally NOT scanned here -- the modules' discipline docstrings name them
# as prose ("No Discord, Telegram, ... reference"); the IMPORT-needle scan above
# is what actually forbids importing those surfaces.
_FORBIDDEN_SURFACE_TERMS: Tuple[str, ...] = (
    "public routing",
    "paid tier",
    "subscriber routing",
    "automated trading",
    "auto-buy",
    "auto buy",
    "private key",
    "signing material",
)


def test_no_forbidden_surface_terms_in_production_modules() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for term in _FORBIDDEN_SURFACE_TERMS:
            assert term not in lower, (
                f"Stage 30.12 module {filename!r} carries forbidden "
                f"surface term {term!r}"
            )


# ---------------------------------------------------------------------------
# 9. No real send call; no filesystem write; no daemon / thread
# ---------------------------------------------------------------------------


def test_production_modules_call_no_real_send_or_io_surface() -> None:
    forbidden_call_substrings = (
        "discord",
        "web" + "hook",
        "urlopen",
        "getenv",
        "environ",
    )
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for bad in forbidden_call_substrings:
                assert bad not in lowered, (
                    f"Stage 30.12 module {filename!r} calls a real send / IO "
                    f"surface {name!r}"
                )


def test_no_filesystem_write_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in ("open(", "Path(", ".write_text(", ".write_bytes("):
            assert needle not in text, (
                f"Stage 30.12 module {filename!r} carries a filesystem "
                f"write surface {needle!r}"
            )


def test_no_while_loop_in_any_production_module() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.12 module {filename!r} carries a while loop"
            )


def test_no_daemon_or_thread_call_or_import_surface() -> None:
    needles = ("daemon", "thread", "spawn", "fork", "sleep")
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.12 module {filename!r} calls a daemon / thread "
                    f"surface {name!r}"
                )
        for module in _imports_of(text):
            lowered = module.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.12 module {filename!r} imports a daemon / "
                    f"thread surface {module!r}"
                )


# ---------------------------------------------------------------------------
# 10. No implicit I/O at import time
# ---------------------------------------------------------------------------
#
# The models + manifest are call-free at module level (pure literals). The
# renderer builds module-level ``re.compile`` / ``frozenset`` constants -- pure
# stdlib, NOT I/O -- so it is exempt from the zero-call check; instead its
# top-level calls are asserted to be ONLY ``re.compile`` / ``frozenset``.


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


def _call_callee_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def test_models_and_manifest_have_no_top_level_call_nodes() -> None:
    for basename in (STAGE30_12_MODELS_BASENAME, STAGE30_12_MANIFEST_BASENAME):
        calls = list(_top_level_call_values(_module_ast(_source_of(basename))))
        assert calls == [], (
            f"Stage 30.12 module {basename!r} carries a top-level call "
            f"(implicit I/O at import time)"
        )


def test_renderer_top_level_calls_are_only_pure_builders() -> None:
    # The renderer builds pure module-level constants at import: compiled
    # regexes (``re.compile``), a base58 / symbol alphabet (``frozenset``), and
    # the price quantum (``Decimal``). None is I/O.
    calls = list(
        _top_level_call_values(_module_ast(_source_of(STAGE30_12_RENDERER_BASENAME)))
    )
    for call in calls:
        assert _call_callee_name(call) in ("compile", "frozenset", "Decimal"), (
            "Stage 30.12 renderer may only build pure re.compile / frozenset / "
            f"Decimal constants at import; found {_call_callee_name(call)!r}"
        )


# ---------------------------------------------------------------------------
# 11. The slice is a LEAF: no existing production file imports it
# ---------------------------------------------------------------------------


_STAGE_30_12_MODULE_PREFIX: str = "PHX2.stage30.stage30_12_"


def test_no_existing_stage30_file_imports_the_slice() -> None:
    own_basenames = set(STAGE30_12_ALLOWED_STAGE30_BASENAMES)
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__" or not entry.name.endswith(".py"):
            continue
        if entry.name in own_basenames:
            continue
        text = entry.read_text(encoding="utf-8")
        for module in _imports_of(text):
            assert not module.startswith(_STAGE_30_12_MODULE_PREFIX), (
                f"{entry.name!r} imports the Stage 30.12 slice ({module!r}); "
                f"the slice is a leaf and is not wired into the runtime"
            )
