"""Stage 30.8.2 production-file boundary tests.

Scans the single Stage 30.8.2 production .py module (the temp-dir
artifact writer) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing``
    / ``dataclasses`` / ``json`` / ``pathlib`` / ``re``) -- the writer
    legitimately needs ``json`` + ``pathlib`` + ``re`` to write JSON to a
    caller temp dir, but nothing more,
  * a positive PHX2 import allowlist (only the Stage 30.8.1 models +
    validators siblings) -- which proves, by construction, that NO Stage
    21-29 / Stage 29.5 / Stage 30.7 / runtime / orchestrator / renderer /
    Discord / provider / network module is imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` / ``os.environb``
    access (the writer reads NO process environment),
  * no database / SQLite / compression surface import (``sqlite3`` / zstd /
    lzma / gzip / zlib / ``shutil`` / ``dbm`` / ``pickle``),
  * no network module import,
  * no Stage 21-29 import, no Stage 29.5 import, no PHX1 import,
  * no Discord / provider / runtime / renderer import surface,
  * no forbidden text needles (URL hosts, inbound-hook hosts, API
    credentials, RPC provider names),
  * zero top-level Call nodes (no implicit I/O at import time),
  * clean import,
  * no Stage 30.8.3+ file admitted by the manifest inventory,
  * no runtime / renderer / model integration (the Stage 30.4 / 30.3
    orchestrator + the compact renderer / models do NOT import the Stage
    30.8.2 writer).

Fake / offline only. No live call, no actual collection root, no Discord.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_8_manifest import (
    STAGE30_8_2_ALLOWED_PHX2_IMPORTS,
    STAGE30_8_2_ALLOWED_STAGE30_BASENAMES,
    STAGE30_8_2_ALLOWED_STDLIB_IMPORTS,
    STAGE30_8_2_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME,
    STAGE30_8_2_TEMP_ARTIFACT_WRITER_MODULE,
    STAGE30_8_2_TEST_BASENAMES,
    STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    STAGE30_8_1_ARTIFACT_VALIDATORS_MODULE,
    STAGE30_8_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scanned_sources() -> Dict[str, str]:
    files: Dict[str, str] = {}
    for basename in STAGE30_8_2_SCANNED_PRODUCTION_BASENAMES:
        path = STAGE30_ROOT / basename
        files[basename] = path.read_text(encoding="utf-8")
    return files


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


# ---------------------------------------------------------------------------
# 1. Files exist + import cleanly
# ---------------------------------------------------------------------------


def test_writer_production_file_exists() -> None:
    for basename in STAGE30_8_2_ALLOWED_STAGE30_BASENAMES:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"Stage 30.8.2 requires {path}"


def test_scanned_production_basename_is_the_writer() -> None:
    assert STAGE30_8_2_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME,
    )


def test_writer_module_imports_cleanly() -> None:
    import PHX2.stage30.stage30_8_temp_artifact_writer  # noqa: F401


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
                module in STAGE30_8_2_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_8_2_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.8.2 module {filename!r} imports "
                f"non-allowlisted stdlib/3rd-party module {module!r}"
            )


def test_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_8_2_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.8.2 module {filename!r} imports "
                f"non-allowlisted PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_the_two_stage_30_8_1_siblings() -> None:
    assert STAGE30_8_2_ALLOWED_PHX2_IMPORTS == (
        STAGE30_8_1_ARTIFACT_MODELS_MODULE,
        STAGE30_8_1_ARTIFACT_VALIDATORS_MODULE,
    )
    for module in STAGE30_8_2_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_8_")


def test_writer_imports_only_the_two_siblings() -> None:
    text = (
        STAGE30_ROOT / STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME
    ).read_text(encoding="utf-8")
    phx2_imports = {
        module
        for module in _imports_of(text)
        if module.startswith("PHX2.")
    }
    assert phx2_imports == {
        STAGE30_8_1_ARTIFACT_MODELS_MODULE,
        STAGE30_8_1_ARTIFACT_VALIDATORS_MODULE,
    }, (
        "Stage 30.8.2 writer must import only the Stage 30.8.1 models + "
        f"validators siblings; found {sorted(phx2_imports)}"
    )


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.8.2 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.8.2 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        tree = _module_ast(text)
        os_aliases: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        os_aliases.add(alias.asname or alias.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id in os_aliases
                    and node.attr in {"environ", "getenv", "environb"}
                ):
                    raise AssertionError(
                        f"Stage 30.8.2 module {filename!r} performs "
                        f"os.{node.attr} access"
                    )


# ---------------------------------------------------------------------------
# 4. No database / compression / network / secret module imports
# ---------------------------------------------------------------------------
#
# ``pathlib`` and ``json`` are intentionally NOT forbidden here (the writer
# needs them); ``os`` IS forbidden (covered above) so no env can be read.


_FORBIDDEN_DB_OR_COMPRESSION_MODULES: Tuple[str, ...] = (
    "sqlite3",
    "zstandard",
    "zstd",
    "lzma",
    "gzip",
    "zlib",
    "bz2",
    "shutil",
    "dbm",
    "pickle",
    "marshal",
)


def test_no_db_or_compression_surface_imports() -> None:
    """No database / SQLite / compression surface may be imported: the
    construction-time proof that Stage 30.8.2 opens no DB and adds no
    compression.
    """
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_DB_OR_COMPRESSION_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.8.2 module {filename!r} imports database / "
                    f"compression surface module {module!r}"
                )


_FORBIDDEN_NETWORK_MODULES: Tuple[str, ...] = (
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
)


def test_no_network_or_secret_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.8.2 module {filename!r} imports "
                    f"network / secret module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / Stage 29.5 / PHX1 import
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
                    f"Stage 30.8.2 module {filename!r} imports Stage "
                    f"21-29 module {module!r}"
                )
            assert "stage29" not in module, (
                f"Stage 30.8.2 module {filename!r} imports Stage 29 / "
                f"29.5 module {module!r}"
            )
            assert not module.startswith("PHX1"), (
                f"Stage 30.8.2 module {filename!r} imports PHX1 "
                f"module {module!r}"
            )


# ---------------------------------------------------------------------------
# 6. No Discord / provider / runtime / renderer import surface
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
    "renderer",
    "runtime",
    "compact_ping",
)


def test_no_provider_runtime_or_renderer_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module in STAGE30_8_2_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.8.2 module {filename!r} imports forbidden "
                    f"surface {needle!r}; offender {module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden secret / transport / URL text needles
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_8_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.8.2 module {filename!r} carries forbidden "
                f"text needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. Zero top-level Call nodes (no implicit I/O at import time)
# ---------------------------------------------------------------------------


def test_no_top_level_call_nodes() -> None:
    """No implicit I/O at import time: the module body carries no
    expression / assignment whose value is a Call. (Class decorators such
    as ``@dataclass(frozen=True)`` live in ``decorator_list``, not in a
    body statement's ``.value``, so they are correctly ignored.)
    """
    for filename, text in _scanned_sources().items():
        tree = _module_ast(text)
        hits = []
        for stmt in tree.body:
            if isinstance(stmt, ast.Expr) and isinstance(
                stmt.value, ast.Call
            ):
                hits.append(ast.dump(stmt.value))
            if isinstance(stmt, ast.Assign) and isinstance(
                stmt.value, ast.Call
            ):
                hits.append(ast.dump(stmt.value))
            if isinstance(stmt, ast.AnnAssign):
                if stmt.value is not None and isinstance(
                    stmt.value, ast.Call
                ):
                    hits.append(ast.dump(stmt.value))
        assert not hits, (
            f"Stage 30.8.2 module {filename!r} must carry zero "
            f"top-level Call nodes; offenders: {hits!r}"
        )


# ---------------------------------------------------------------------------
# 9. No Stage 30.8.3+ file admitted by the manifest inventory
# ---------------------------------------------------------------------------


# Matches any Stage 30.8.<N> minor-version token in a basename (both the
# production ``stage30_8_<N>`` and the test ``stage_30_8_<N>`` spellings).
# A captured N >= 3 is a future Stage 30.8.3+ file that must not yet be
# admitted; N in {0, 1, 2} is allowed.
_STAGE_30_8_MINOR_RE = re.compile(r"stage_?30_8_(\d+)")


def _future_30_8_violations(basenames: Tuple[str, ...]) -> list:
    violations = []
    for basename in basenames:
        for match in _STAGE_30_8_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 3:
                violations.append(basename)
    return violations


def test_manifest_inventory_admits_no_stage_30_8_3_plus_file() -> None:
    # Generic guard: catch ANY Stage 30.8.3+ minor (30_8_3, 30_8_4,
    # 30_8_5, ... 30_8_<N>), not just an enumerated 3/4.
    inventory = (
        tuple(STAGE30_8_2_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_8_2_TEST_BASENAMES)
    )
    violations = _future_30_8_violations(inventory)
    assert violations == [], (
        "Stage 30.8.2 manifest inventory must not admit a Stage 30.8.3+ "
        f"file yet; saw {violations!r}"
    )


# ---------------------------------------------------------------------------
# 10. No runtime / renderer / model integration of the Stage 30.8.2 writer
# ---------------------------------------------------------------------------
#
# Stage 30.8.2 is a standalone temp-dir writer: no live runtime path, no
# renderer, and no compact model imports it. These pins assert the writer
# stays disconnected from the runtime orchestrator + compact renderer /
# models (the writer module name / dotted path appears in none of them).


_RUNTIME_FILES_THAT_MUST_NOT_IMPORT_WRITER: Tuple[str, ...] = (
    "stage30_4_compact_runtime_session_orchestrator.py",
    "stage30_3_compact_runtime_session_orchestrator.py",
    "compact_ping_renderer.py",
    "compact_ping_models.py",
)


def test_runtime_and_renderer_do_not_import_writer() -> None:
    for basename in _RUNTIME_FILES_THAT_MUST_NOT_IMPORT_WRITER:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"expected {path} to exist"
        text = path.read_text(encoding="utf-8")
        assert STAGE30_8_2_TEMP_ARTIFACT_WRITER_MODULE not in text, (
            f"{basename!r} must not reference the Stage 30.8.2 writer "
            f"module {STAGE30_8_2_TEMP_ARTIFACT_WRITER_MODULE!r}"
        )
        assert "stage30_8_temp_artifact_writer" not in text, (
            f"{basename!r} must not import the Stage 30.8.2 writer"
        )
        # And it does not import the writer's bundle / entry-point symbols.
        for module in _imports_of(text):
            assert "stage30_8_temp_artifact_writer" not in module, (
                f"{basename!r} imports the Stage 30.8.2 writer {module!r}"
            )
