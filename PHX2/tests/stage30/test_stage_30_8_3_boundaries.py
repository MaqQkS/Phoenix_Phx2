"""Stage 30.8.3 production-file boundary tests.

Scans the three Stage 30.8.3 production .py modules (the index models,
the manifest-backed bundle reader, the index / dedupe builder) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses`` / ``json`` / ``pathlib``; the models need only
    ``dataclasses``, the reader adds ``json`` + ``pathlib``, the builder
    adds ``pathlib``),
  * a positive PHX2 import allowlist (the models + reader import NO PHX2
    module; only the builder imports PHX2 -- exactly the Stage 30.8.3
    reader + index-models siblings plus the Stage 30.8.1 artifact-models
    sibling) -- which proves, by construction, that NO Stage 21-29 / Stage
    29.5 / Stage 30.7 / runtime / orchestrator / renderer / Discord /
    provider / network module is imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` access,
  * no database / SQLite / compression surface import,
  * no network module import,
  * no Stage 21-29 / Stage 29.5 / PHX1 import,
  * no Discord / provider / runtime / renderer import surface,
  * no forbidden secret / transport / URL text needles,
  * zero top-level Call nodes (no implicit I/O at import time),
  * READ-ONLY: no filesystem WRITE operation anywhere in the slice,
  * no Stage 30.8.4+ file admitted by the manifest inventory,
  * no runtime / renderer / model integration (the orchestrator + compact
    renderer / models do NOT import the Stage 30.8.3 modules).

Fake / offline only. No live call, no actual collection root, no Discord.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_8_manifest import (
    STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    STAGE30_8_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_8_3_ALLOWED_STAGE30_BASENAMES,
    STAGE30_8_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_8_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_8_3_SESSION_BUNDLE_READER_BASENAME,
    STAGE30_8_3_SESSION_BUNDLE_READER_MODULE,
    STAGE30_8_3_SESSION_INDEX_BUILDER_BASENAME,
    STAGE30_8_3_SESSION_INDEX_MODELS_BASENAME,
    STAGE30_8_3_SESSION_INDEX_MODELS_MODULE,
    STAGE30_8_3_TEST_BASENAMES,
    STAGE30_8_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scanned_sources() -> Dict[str, str]:
    files: Dict[str, str] = {}
    for basename in STAGE30_8_3_SCANNED_PRODUCTION_BASENAMES:
        files[basename] = (STAGE30_ROOT / basename).read_text(
            encoding="utf-8"
        )
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


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Files exist + import cleanly
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_8_3_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.8.3 requires {basename}"
        )


def test_scanned_basenames_are_the_three_modules() -> None:
    assert STAGE30_8_3_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_8_3_SESSION_INDEX_MODELS_BASENAME,
        STAGE30_8_3_SESSION_BUNDLE_READER_BASENAME,
        STAGE30_8_3_SESSION_INDEX_BUILDER_BASENAME,
    )


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_8_session_index_models  # noqa: F401
    import PHX2.stage30.stage30_8_session_bundle_reader  # noqa: F401
    import PHX2.stage30.stage30_8_session_index_builder  # noqa: F401


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
                module in STAGE30_8_3_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_8_3_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.8.3 module {filename!r} imports "
                f"non-allowlisted stdlib/3rd-party module {module!r}"
            )


def test_models_and_reader_import_no_phx2_module() -> None:
    for basename in (
        STAGE30_8_3_SESSION_INDEX_MODELS_BASENAME,
        STAGE30_8_3_SESSION_BUNDLE_READER_BASENAME,
    ):
        phx2 = {m for m in _imports_of(_source_of(basename)) if m.startswith("PHX2.")}
        assert phx2 == set(), (
            f"Stage 30.8.3 module {basename!r} must import no PHX2 module; "
            f"found {sorted(phx2)}"
        )


def test_models_module_is_filesystem_free() -> None:
    # The passive index models must not reach any filesystem / json surface.
    imports = _imports_of(_source_of(STAGE30_8_3_SESSION_INDEX_MODELS_BASENAME))
    for module in imports:
        top = module.split(".")[0]
        assert top in ("__future__", "typing", "dataclasses"), (
            "Stage 30.8.3 index models must import only __future__ / "
            f"typing / dataclasses; saw {module!r}"
        )


def test_builder_phx2_imports_are_exactly_the_allowlist() -> None:
    phx2 = {
        m
        for m in _imports_of(
            _source_of(STAGE30_8_3_SESSION_INDEX_BUILDER_BASENAME)
        )
        if m.startswith("PHX2.")
    }
    assert phx2 == {
        STAGE30_8_3_SESSION_INDEX_MODELS_MODULE,
        STAGE30_8_3_SESSION_BUNDLE_READER_MODULE,
        STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    }, (
        "Stage 30.8.3 builder must import only the Stage 30.8.3 reader + "
        f"index-models + Stage 30.8.1 artifact-models siblings; found "
        f"{sorted(phx2)}"
    )


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_8_3_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.8.3 module {filename!r} imports "
                f"non-allowlisted PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_stage_30_8_siblings_only() -> None:
    for module in STAGE30_8_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_8_")


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.8.3 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.8.3 module {filename!r} imports {module!r}"
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
                        f"Stage 30.8.3 module {filename!r} performs "
                        f"os.{node.attr} access"
                    )


# ---------------------------------------------------------------------------
# 4. No database / compression / network / secret module imports
# ---------------------------------------------------------------------------


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
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_DB_OR_COMPRESSION_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.8.3 module {filename!r} imports database / "
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
                    f"Stage 30.8.3 module {filename!r} imports "
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
                    f"Stage 30.8.3 module {filename!r} imports Stage "
                    f"21-29 module {module!r}"
                )
            assert "stage29" not in module, (
                f"Stage 30.8.3 module {filename!r} imports Stage 29 / "
                f"29.5 module {module!r}"
            )
            assert not module.startswith("PHX1"), (
                f"Stage 30.8.3 module {filename!r} imports PHX1 "
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
            if module in STAGE30_8_3_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.8.3 module {filename!r} imports forbidden "
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
                f"Stage 30.8.3 module {filename!r} carries forbidden "
                f"text needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. Zero top-level Call nodes (no implicit I/O at import time)
# ---------------------------------------------------------------------------


def test_no_top_level_call_nodes() -> None:
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
            f"Stage 30.8.3 module {filename!r} must carry zero "
            f"top-level Call nodes; offenders: {hits!r}"
        )


# ---------------------------------------------------------------------------
# 9. READ-ONLY: no filesystem write operation anywhere in the slice
# ---------------------------------------------------------------------------


_WRITE_OP_TOKENS: Tuple[str, ...] = (
    "write_text",
    "write_bytes",
    "mkdir",
    ".rename(",
    ".replace(",
    ".unlink(",
    ".rmdir(",
    ".touch(",
    "open(",
)


def test_slice_performs_no_filesystem_write() -> None:
    """Stage 30.8.3 reads bundles and enumerates dirs; it WRITES NOTHING.
    No production module may carry a filesystem write operation.
    """
    for filename, text in _scanned_sources().items():
        for token in _WRITE_OP_TOKENS:
            assert token not in text, (
                f"Stage 30.8.3 module {filename!r} carries a write "
                f"operation {token!r}; the slice must be read-only"
            )


# ---------------------------------------------------------------------------
# 10. No Stage 30.8.4+ file admitted by the manifest inventory
# ---------------------------------------------------------------------------


# Matches a Stage 30.8.<N> minor token; N >= 4 is a future Stage 30.8.4+
# file that must not yet be admitted; N in {0, 1, 2, 3} is allowed.
_STAGE_30_8_MINOR_RE = re.compile(r"stage_?30_8_(\d+)")


def _future_30_8_violations(basenames: Tuple[str, ...]) -> list:
    violations = []
    for basename in basenames:
        for match in _STAGE_30_8_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 4:
                violations.append(basename)
    return violations


def test_manifest_inventory_admits_no_stage_30_8_4_plus_file() -> None:
    inventory = (
        tuple(STAGE30_8_3_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_8_3_TEST_BASENAMES)
    )
    violations = _future_30_8_violations(inventory)
    assert violations == [], (
        "Stage 30.8.3 manifest inventory must not admit a Stage 30.8.4+ "
        f"file yet; saw {violations!r}"
    )


# ---------------------------------------------------------------------------
# 11. No runtime / renderer / model integration of the Stage 30.8.3 modules
# ---------------------------------------------------------------------------


_RUNTIME_FILES_THAT_MUST_NOT_IMPORT_THE_SLICE: Tuple[str, ...] = (
    "stage30_4_compact_runtime_session_orchestrator.py",
    "stage30_3_compact_runtime_session_orchestrator.py",
    "compact_ping_renderer.py",
    "compact_ping_models.py",
    "stage30_8_temp_artifact_writer.py",
    "stage30_8_artifact_models.py",
    "stage30_8_artifact_validators.py",
)


def test_runtime_renderer_and_writer_do_not_import_the_slice() -> None:
    slice_modules = (
        "stage30_8_session_index_models",
        "stage30_8_session_bundle_reader",
        "stage30_8_session_index_builder",
    )
    for basename in _RUNTIME_FILES_THAT_MUST_NOT_IMPORT_THE_SLICE:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"expected {path} to exist"
        text = path.read_text(encoding="utf-8")
        for module in slice_modules:
            assert module not in text, (
                f"{basename!r} must not reference the Stage 30.8.3 "
                f"module {module!r}"
            )
