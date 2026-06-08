"""Stage 30.11.16 real-send guard boundary tests.

Scans the three Stage 30.11.16 production .py modules (the real-send models, the
real private transport guard, the fake real-send proof) for:

  * a positive stdlib import allowlist (``__future__`` / ``typing`` /
    ``dataclasses`` ONLY -- no os / json / pathlib / datetime / decimal / network);
  * a positive PHX2 import allowlist (the own siblings plus the committed Stage
    30.11.15 deduped-result + dedupe-outcome types the guard consumes) -- proving
    NO Stage 21-29 import and in particular NO Stage 28 transport import (the
    audited transport is injected duck-typed);
  * no ``os.environ`` / ``os.getenv`` access;
  * no database / SQLite / compression surface import;
  * no network / concurrency / clock import;
  * no forbidden secret / transport / URL text needle (the family set MINUS the
    ``authorization`` keyword the slice uses for OPERATOR authorization -- mirrors
    the Stage 30.11.15 ``endpoint_secret`` deviation) and no ``://`` literal;
  * no filesystem write surface (the guard owns no persistence -- it touches no
    ledger);
  * no implicit I/O at import time (zero top-level Call nodes);
  * no unbounded ``while`` loop / daemon / thread surface;
  * the Stage 30.11.16 inventory admits no Stage 30.11.17+ / Stage 31 file.

Fake / no-send only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_16_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_16_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_16_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_16_REAL_PRIVATE_TRANSPORT_GUARD_BASENAME,
    STAGE30_11_16_REAL_SEND_MODELS_BASENAME,
    STAGE30_11_16_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_16_TEST_BASENAMES,
    STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# The Stage 30.11.16 text-needle set: the family set MINUS the ``authorization``
# keyword the slice uses for OPERATOR authorization (a safe domain word -- the
# authorization sentinel / its reason field -- not an HTTP auth-header value).
# Mirrors the committed Stage 30.11.15 needle-set deviation.
_AUTHORIZATION_NEEDLE: str = "author" + "ization"
_NEEDLES: Tuple[str, ...] = tuple(
    n for n in STAGE30_11_FORBIDDEN_TEXT_NEEDLES if n != _AUTHORIZATION_NEEDLE
)


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_11_16_SCANNED_PRODUCTION_BASENAMES
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
# 1. Files exist + scanned set is the three modules + import cleanly
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_11_16_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.16 requires {basename}"
        )


def test_scanned_basenames_are_the_three_modules() -> None:
    assert STAGE30_11_16_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_16_ALLOWED_STAGE30_BASENAMES
    )
    assert len(STAGE30_11_16_SCANNED_PRODUCTION_BASENAMES) == 3


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_11_16_real_send_models  # noqa: F401
    import PHX2.stage30.stage30_11_16_real_private_transport_guard  # noqa: F401
    import PHX2.stage30.stage30_11_16_fake_real_send_proof  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Positive stdlib + PHX2 import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_in_base_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            top = module.split(".")[0]
            assert (
                module in STAGE30_11_16_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_11_16_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.11.16 module {filename!r} imports non-allowlisted "
                f"stdlib module {module!r}"
            )


def test_stdlib_allowlist_excludes_io_db_and_clock() -> None:
    for forbidden in (
        "os",
        "json",
        "pathlib",
        "datetime",
        "decimal",
        "sqlite3",
        "time",
    ):
        assert forbidden not in STAGE30_11_16_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_11_16_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.11.16 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_phx2_allowlist_stays_within_stage30_family() -> None:
    for module in STAGE30_11_16_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_16_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "renderer", "live_provider", "stage28"):
        assert forbidden not in joined


def test_models_module_imports_no_phx2() -> None:
    # The models module is a pure leaf (mirrors the Stage 30.11.15 models).
    assert _phx2_imports_of(STAGE30_11_16_REAL_SEND_MODELS_BASENAME) == set()


def test_guard_consumes_the_committed_deduped_result() -> None:
    phx2 = _phx2_imports_of(
        STAGE30_11_16_REAL_PRIVATE_TRANSPORT_GUARD_BASENAME
    )
    assert "PHX2.stage30.stage30_11_15_no_send_dedupe_guard" in phx2, (
        "the Stage 30.11.16 guard must consume the committed Stage 30.11.15 "
        "deduped compose result"
    )


# ---------------------------------------------------------------------------
# 3. No Stage 28 import + no env / db / network / stage21-29 / PHX1 imports
# ---------------------------------------------------------------------------


def test_no_stage28_import() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            assert not (
                module == "PHX2.stage28"
                or module.startswith("PHX2.stage28.")
            ), (
                f"Stage 30.11.16 module {filename!r} imports Stage 28 "
                f"{module!r}; the audited transport must be injected duck-typed"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.11.16 module {filename!r} performs "
                    f"os.{node.attr} access"
                )


_FORBIDDEN_DB_OR_COMPRESSION_MODULES: Tuple[str, ...] = (
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
                    f"Stage 30.11.16 module {filename!r} imports database / "
                    f"compression surface {module!r}"
                )


_FORBIDDEN_NETWORK_OR_CONCURRENCY_MODULES: Tuple[str, ...] = (
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
)


def test_no_network_concurrency_or_clock_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_OR_CONCURRENCY_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.11.16 module {filename!r} imports forbidden "
                    f"network / concurrency / clock module {module!r}"
                )


def test_no_stage21_29_or_phx1_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for stage_n in range(21, 30):
                prefix = f"PHX2.stage{stage_n}"
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.11.16 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.11.16 module {filename!r} imports PHX1 {module!r}"
            )


# ---------------------------------------------------------------------------
# 4. No forbidden secret / transport / URL needles + no scheme literal
# ---------------------------------------------------------------------------


def test_needle_set_deviation_is_only_authorization() -> None:
    family = set(STAGE30_11_FORBIDDEN_TEXT_NEEDLES)
    own = set(_NEEDLES)
    assert family - own == {_AUTHORIZATION_NEEDLE}
    # The genuinely-forbidden URL / secret / host needles are all retained.
    for needle in (
        "discord" + ".com",
        "/web" + "hooks/",
        "b" + "earer",
        "api_" + "key",
        "h" + "ttps://",
        "chain" + "stack",
        "hel" + "ius",
    ):
        assert needle in own


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in _NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.11.16 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.11.16 module {filename!r} carries a transport scheme "
            f"literal"
        )


# ---------------------------------------------------------------------------
# 5. No filesystem-write surface (the guard touches no ledger / persistence)
# ---------------------------------------------------------------------------


_FS_WRITE_NEEDLES: Tuple[str, ...] = (
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
                f"Stage 30.11.16 module {filename!r} carries a filesystem "
                f"surface {needle!r} (the guard owns no persistence)"
            )


# ---------------------------------------------------------------------------
# 6. No implicit I/O at import time + no unbounded loop / daemon / thread
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
            f"Stage 30.11.16 module {filename!r} carries a top-level call "
            f"(implicit I/O at import time)"
        )


def test_no_while_loop_in_any_production_module() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.11.16 module {filename!r} carries a while loop"
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
                    f"Stage 30.11.16 module {filename!r} calls a daemon / "
                    f"thread surface {name!r}"
                )


# ---------------------------------------------------------------------------
# 7. No Stage 30.11.17+ / Stage 31 file admitted by the Stage 30.11.16 inventory
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_11_17_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_11_16_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_16_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_11_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 16, (
                "Stage 30.11.16 inventory must not admit a Stage 30.11.17+ "
                f"file; offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.11.16 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )
