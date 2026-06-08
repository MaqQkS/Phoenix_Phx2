"""Stage 30.11.15 committed cross-run ping dedupe boundary tests.

Scans the four Stage 30.11.15 production .py modules (the dedupe models, the
ping dedupe ledger, the no-send dedupe guard + orchestrator, the fake dedupe
proof) for:

  * a positive stdlib import allowlist -- the NON-ledger modules (models / guard
    / fake proof) admit only ``__future__`` / ``typing`` / ``dataclasses`` /
    ``decimal`` (NO os / json / pathlib / datetime); the LEDGER alone admits
    ``json`` / ``pathlib`` / ``datetime`` (its ``Path.open`` filesystem append +
    parse-only TTL surface; NO ``os`` -- the global Stage 30 import guard forbids
    it);
  * a positive PHX2 import allowlist (the own siblings plus the committed Stage
    30.11.13 composer + its fake-proof request factory + the committed Stage
    30.11.5 recording fake transport client) -- proving NO Stage 21-29 / runtime
    orchestrator / renderer / real transport / provider / Discord / network
    module is imported,
  * no ``os.environ`` / ``os.getenv`` access,
  * no database / SQLite / compression surface import,
  * no network / concurrency import (datetime is allowed in the ledger ONLY, for
    PARSE-only TTL math; the ledger never calls ``datetime.now`` / ``utcnow``),
  * no Stage 21-29 / PHX1 import,
  * no forbidden secret / transport / URL text needle (the family set MINUS the
    ``endpoint_secret`` keyword the guard / proof forward to the committed
    composer -- mirrors Stage 30.11.11) and no ``://`` literal,
  * filesystem write surfaces (``open(`` / ``Path(`` / ``.write_text`` /
    ``.write_bytes``) ONLY in the ledger module -- the composer itself still
    carries none,
  * no implicit I/O at import time (zero top-level Call nodes),
  * no unbounded ``while`` loop / daemon / thread surface,
  * the Stage 30.11.15 inventory admits no Stage 30.11.16+ / Stage 31 file.

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_15_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_15_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_15_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_15_LEDGER_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_15_NO_SEND_DEDUPE_GUARD_BASENAME,
    STAGE30_11_15_PING_DEDUPE_LEDGER_BASENAME,
    STAGE30_11_15_PING_DEDUPE_MODELS_BASENAME,
    STAGE30_11_15_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_15_STAGE30_11_13_COMPOSER_MODULE,
    STAGE30_11_15_TEST_BASENAMES,
    STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"

_LEDGER_BASENAME: str = STAGE30_11_15_PING_DEDUPE_LEDGER_BASENAME
_COMPOSER_BASENAME: str = "stage30_11_13_committed_no_send_composer.py"

# The Stage 30.11.15 text-needle set: the family set MINUS the ``endpoint_secret``
# KEYWORD the guard + fake proof forward to the committed composer's injected ATH
# endpoint-secret carrier (a safe param name, not a secret value). Mirrors the
# committed Stage 30.11.11 needle-set deviation.
_ENDPOINT_SECRET_NEEDLE: str = "endpoint" + "_secret"
_NEEDLES: Tuple[str, ...] = tuple(
    n for n in STAGE30_11_FORBIDDEN_TEXT_NEEDLES if n != _ENDPOINT_SECRET_NEEDLE
)


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_11_15_SCANNED_PRODUCTION_BASENAMES
    }


def _non_ledger_sources() -> Dict[str, str]:
    return {
        basename: text
        for basename, text in _scanned_sources().items()
        if basename != _LEDGER_BASENAME
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
# 1. Files exist + scanned set is the four modules + import cleanly
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_11_15_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.15 requires {basename}"
        )


def test_scanned_basenames_are_the_four_modules() -> None:
    assert STAGE30_11_15_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_15_ALLOWED_STAGE30_BASENAMES
    )
    assert len(STAGE30_11_15_SCANNED_PRODUCTION_BASENAMES) == 4


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_11_15_ping_dedupe_models  # noqa: F401
    import PHX2.stage30.stage30_11_15_ping_dedupe_ledger  # noqa: F401
    import PHX2.stage30.stage30_11_15_no_send_dedupe_guard  # noqa: F401
    import PHX2.stage30.stage30_11_15_fake_dedupe_proof  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Positive stdlib + PHX2 import allowlists (per-module)
# ---------------------------------------------------------------------------


def test_non_ledger_stdlib_in_base_allowlist() -> None:
    for filename, text in _non_ledger_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            top = module.split(".")[0]
            assert (
                module in STAGE30_11_15_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_11_15_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.11.15 non-ledger module {filename!r} imports "
                f"non-allowlisted stdlib module {module!r}"
            )


def test_base_stdlib_allowlist_excludes_io_db_and_clock() -> None:
    for forbidden in ("os", "json", "pathlib", "datetime", "sqlite3", "time"):
        assert forbidden not in STAGE30_11_15_ALLOWED_STDLIB_IMPORTS


def test_ledger_stdlib_in_ledger_allowlist() -> None:
    for module in _imports_of(_source_of(_LEDGER_BASENAME)):
        if module.startswith("PHX2."):
            continue
        top = module.split(".")[0]
        assert (
            module in STAGE30_11_15_LEDGER_ALLOWED_STDLIB_IMPORTS
            or top in STAGE30_11_15_LEDGER_ALLOWED_STDLIB_IMPORTS
        ), (
            f"Stage 30.11.15 ledger imports non-allowlisted stdlib module "
            f"{module!r}"
        )


def test_ledger_allowlist_is_base_plus_io_and_parse_clock() -> None:
    for needed in ("json", "pathlib", "datetime"):
        assert needed in STAGE30_11_15_LEDGER_ALLOWED_STDLIB_IMPORTS
    # NO ``os`` (the global Stage 30 import guard forbids it; the ledger appends
    # via ``Path.open``), and NO database / compression surface.
    for forbidden in ("os", "sqlite3", "zstandard", "shutil", "time"):
        assert forbidden not in STAGE30_11_15_LEDGER_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_11_15_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.11.15 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_phx2_allowlist_stays_within_stage30_family() -> None:
    for module in STAGE30_11_15_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_15_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


def test_models_module_imports_no_phx2() -> None:
    # The models module is a pure leaf (mirrors the Stage 30.11.3 models).
    assert _phx2_imports_of(STAGE30_11_15_PING_DEDUPE_MODELS_BASENAME) == set()


def test_guard_composes_the_committed_composer() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_15_NO_SEND_DEDUPE_GUARD_BASENAME)
    assert STAGE30_11_15_STAGE30_11_13_COMPOSER_MODULE in phx2, (
        "the Stage 30.11.15 guard / orchestrator must compose the committed "
        "Stage 30.11.13 composer"
    )


# ---------------------------------------------------------------------------
# 3. No env / db / network / stage21-29 / PHX1 imports
# ---------------------------------------------------------------------------


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.11.15 module {filename!r} performs "
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
                    f"Stage 30.11.15 module {filename!r} imports database / "
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
)


def test_no_network_or_concurrency_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_OR_CONCURRENCY_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.11.15 module {filename!r} imports forbidden "
                    f"network / concurrency module {module!r}"
                )


def test_only_the_ledger_imports_datetime() -> None:
    # ``datetime`` is the parse-only TTL surface and belongs ONLY to the ledger.
    for filename, text in _non_ledger_sources().items():
        assert "datetime" not in _imports_of(text), (
            f"Stage 30.11.15 non-ledger module {filename!r} imports datetime"
        )


def test_ledger_never_reads_a_wall_clock() -> None:
    # AST-based (a docstring may NAME ``datetime.now`` in a negative claim): no
    # attribute access resolves to a current-time reader. ``datetime`` is used
    # to PARSE injected timestamps only.
    tree = _module_ast(_source_of(_LEDGER_BASENAME))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("now", "utcnow", "monotonic"), (
                f"Stage 30.11.15 ledger reads a wall clock (.{node.attr}); TTL "
                f"timestamps must be parse-only / injected"
            )


def test_no_stage21_29_or_phx1_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for stage_n in range(21, 30):
                prefix = f"PHX2.stage{stage_n}"
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.11.15 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.11.15 module {filename!r} imports PHX1 {module!r}"
            )


# ---------------------------------------------------------------------------
# 4. No forbidden secret / transport / URL needles + no scheme literal
# ---------------------------------------------------------------------------


def test_needle_set_omits_only_endpoint_secret_vs_family() -> None:
    family = set(STAGE30_11_FORBIDDEN_TEXT_NEEDLES)
    own = set(_NEEDLES)
    assert family - own == {_ENDPOINT_SECRET_NEEDLE}
    # The genuinely-forbidden URL / secret needles are all retained.
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
                f"Stage 30.11.15 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.11.15 module {filename!r} carries a transport scheme "
            f"literal"
        )


# ---------------------------------------------------------------------------
# 5. Filesystem-write surface ONLY in the ledger; composer still has none
# ---------------------------------------------------------------------------


_FS_WRITE_NEEDLES: Tuple[str, ...] = (
    "open(",
    "Path(",
    ".write_text(",
    ".write_bytes(",
    ".mkdir(",
)


def test_filesystem_surface_only_in_the_ledger() -> None:
    for filename, text in _non_ledger_sources().items():
        for needle in _FS_WRITE_NEEDLES:
            assert needle not in text, (
                f"Stage 30.11.15 non-ledger module {filename!r} carries a "
                f"filesystem surface {needle!r} (persistence belongs to the "
                f"ledger only)"
            )


def test_ledger_is_the_persistence_surface() -> None:
    text = _source_of(_LEDGER_BASENAME)
    assert "open(" in text, (
        "the Stage 30.11.15 ledger is the append-only persistence surface"
    )


def test_composer_still_has_no_filesystem_write_surface() -> None:
    text = _source_of(_COMPOSER_BASENAME)
    for needle in ("open(", "Path(", ".write_text(", ".write_bytes("):
        assert needle not in text, (
            f"the committed composer must remain file-free; saw {needle!r}"
        )
    for module in _imports_of(text):
        assert module not in ("os", "json", "pathlib"), (
            f"the committed composer must not import an I/O module ({module!r})"
        )


# ---------------------------------------------------------------------------
# 6. No implicit I/O at import time + no unbounded loop / daemon
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
            f"Stage 30.11.15 module {filename!r} carries a top-level call "
            f"(implicit I/O at import time)"
        )


def test_no_while_loop_in_any_production_module() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.11.15 module {filename!r} carries a while loop"
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
                    f"Stage 30.11.15 module {filename!r} calls a daemon / "
                    f"thread surface {name!r}"
                )


# ---------------------------------------------------------------------------
# 7. No Stage 30.11.16+ / Stage 31 file admitted by the Stage 30.11.15 inventory
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_11_16_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_11_15_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_15_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_11_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 15, (
                "Stage 30.11.15 inventory must not admit a Stage 30.11.16+ "
                f"file; offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.11.15 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )
