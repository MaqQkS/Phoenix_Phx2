"""Stage 30.8.1 production-file boundary tests.

Scans the two Stage 30.8.1 production .py modules (artifact models +
artifact validators) for:

  * a positive stdlib import allowlist (only ``__future__`` /
    ``typing`` / ``dataclasses`` / ``math``),
  * a positive PHX2 import allowlist (the validators import only the
    Stage 30.8.1 models sibling; the models import NO PHX2 module) --
    which proves, by construction, that NO Stage 21-29 / Stage 29.5 /
    Stage 30.7 / runtime / orchestrator / renderer / Discord / provider
    / network / disk module is imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` /
    ``os.environb`` access,
  * no disk / storage / database / compression surface import
    (``os`` / ``pathlib`` / ``shutil`` / ``sqlite3`` / zstd / lzma /
    gzip / zlib) -- so NO file is written and NO actual disk is read,
  * no network module import,
  * no Stage 21-29 import, no Stage 29.5 import, no PHX1 import,
  * no Discord / provider import surface,
  * no forbidden text needles (URL hosts, inbound-hook hosts, API
    credentials, RPC provider names),
  * no transport-construction / filesystem-write / disk-read needles,
  * no writer-like function definition / method-call name (``write`` /
    ``flush`` / ``persist`` / ``save`` / ``append_jsonl`` /
    ``database`` / ``sqlite`` / ``zstd``),
  * no ``open(`` call,
  * zero top-level Call nodes (no implicit I/O at import time),
  * clean import,
  * no Stage 30.8.2+ file admitted by the manifest inventory.

Fake / offline only. No live call, no actual-disk read, no file write.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_8_manifest import (
    STAGE30_8_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_8_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_8_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_8_1_ARTIFACT_MODELS_BASENAME,
    STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    STAGE30_8_1_ARTIFACT_VALIDATORS_BASENAME,
    STAGE30_8_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_8_1_TEST_BASENAMES,
    STAGE30_8_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scanned_sources() -> Dict[str, str]:
    files: Dict[str, str] = {}
    for basename in STAGE30_8_1_SCANNED_PRODUCTION_BASENAMES:
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


def test_all_production_files_exist() -> None:
    for basename in STAGE30_8_1_ALLOWED_STAGE30_BASENAMES:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"Stage 30.8.1 requires {path}"


def test_scanned_production_basenames_are_the_two_modules() -> None:
    assert STAGE30_8_1_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_8_1_ARTIFACT_MODELS_BASENAME,
        STAGE30_8_1_ARTIFACT_VALIDATORS_BASENAME,
    )


def test_every_production_module_imports_cleanly() -> None:
    import PHX2.stage30.stage30_8_artifact_models  # noqa: F401
    import PHX2.stage30.stage30_8_artifact_validators  # noqa: F401


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
                module in STAGE30_8_1_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_8_1_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.8.1 module {filename!r} imports "
                f"non-allowlisted stdlib/3rd-party module {module!r}"
            )


def test_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_8_1_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.8.1 module {filename!r} imports "
                f"non-allowlisted PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_only_the_models_sibling() -> None:
    assert STAGE30_8_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_8_1_ARTIFACT_MODELS_MODULE,
    )
    for module in STAGE30_8_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_8_")


def test_models_module_imports_no_phx2_module() -> None:
    text = (
        STAGE30_ROOT / STAGE30_8_1_ARTIFACT_MODELS_BASENAME
    ).read_text(encoding="utf-8")
    phx2_imports = {
        module
        for module in _imports_of(text)
        if module.startswith("PHX2.")
    }
    assert phx2_imports == set(), (
        "Stage 30.8.1 models module must import no PHX2 module; "
        f"found {sorted(phx2_imports)}"
    )


def test_validators_import_only_the_models_sibling() -> None:
    text = (
        STAGE30_ROOT / STAGE30_8_1_ARTIFACT_VALIDATORS_BASENAME
    ).read_text(encoding="utf-8")
    phx2_imports = {
        module
        for module in _imports_of(text)
        if module.startswith("PHX2.")
    }
    assert phx2_imports == {STAGE30_8_1_ARTIFACT_MODELS_MODULE}, (
        "Stage 30.8.1 validators module must import only the models "
        f"sibling; found {sorted(phx2_imports)}"
    )


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.8.1 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.8.1 module {filename!r} imports {module!r}"
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
                        f"Stage 30.8.1 module {filename!r} performs "
                        f"os.{node.attr} access"
                    )


# ---------------------------------------------------------------------------
# 4. No disk / storage / network / secret module imports
# ---------------------------------------------------------------------------


_FORBIDDEN_DISK_OR_STORAGE_MODULES: Tuple[str, ...] = (
    "os",
    "pathlib",
    "shutil",
    "sqlite3",
    "zstandard",
    "zstd",
    "lzma",
    "gzip",
    "zlib",
)


def test_no_disk_or_storage_surface_imports() -> None:
    """No filesystem / disk / database / compression surface may be
    imported: the construction-time proof that Stage 30.8.1 writes NO
    file and adds NO compression.
    """
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_DISK_OR_STORAGE_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.8.1 module {filename!r} imports disk / "
                    f"storage surface module {module!r}"
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
)


def test_no_network_or_secret_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.8.1 module {filename!r} imports "
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
                    f"Stage 30.8.1 module {filename!r} imports Stage "
                    f"21-29 module {module!r}"
                )
            # Stage 29.5 lives under the Stage 29 surface; any module
            # naming ``stage29`` is forbidden.
            assert "stage29" not in module, (
                f"Stage 30.8.1 module {filename!r} imports Stage 29 / "
                f"29.5 module {module!r}"
            )
            assert not module.startswith("PHX1"), (
                f"Stage 30.8.1 module {filename!r} imports PHX1 "
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
    "transport",
    "compact_ping",
    "artifact_writer",
)


def test_no_provider_runtime_or_renderer_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module == STAGE30_8_1_ARTIFACT_MODELS_MODULE:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.8.1 module {filename!r} imports forbidden "
                    f"surface {needle!r}; offender {module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden text / transport / filesystem / disk-read needles
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_8_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.8.1 module {filename!r} carries forbidden "
                f"text needle {needle!r}"
            )


def test_no_transport_or_filesystem_or_disk_read_needles() -> None:
    needles = (
        # Transport construction.
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "requests." + "post",
        "requests." + "get",
        "url" + "open",
        # Filesystem write.
        "open(",
        ".write_" + "text",
        ".write_" + "bytes",
        "pathlib.",
        "sqlite3.",
        "append_" + "jsonl",
        # Disk read (OS disk-usage APIs).
        "shutil." + "disk_usage",
        "os." + "statvfs",
        "statvfs",
        "GetDiskFreeSpace",
    )
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in needles:
            assert needle.lower() not in lower, (
                f"Stage 30.8.1 module {filename!r} carries forbidden "
                f"transport / filesystem / disk-read needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. No writer-like definitions / calls
# ---------------------------------------------------------------------------
#
# Writer-like NAMES are forbidden as function / method DEFINITIONS and as
# attribute CALL targets. They are intentionally NOT scanned as bare
# substrings: the mandated validation-verdict field ``safe_to_persist``
# (a passive boolean, not a writer) and the Stage 30.6 byte-counter
# fields ``raw_bytes_written`` / ``durable_rows_written`` (passive data,
# not methods) are legitimate and must not trip this guard.


_WRITER_NAME_TOKENS: Tuple[str, ...] = (
    "write",
    "flush",
    "persist",
    "save",
    "append_jsonl",
    "database",
    "sqlite",
    "zstd",
)


def test_no_writer_like_function_definitions() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                lower = node.name.lower()
                for token in _WRITER_NAME_TOKENS:
                    assert token not in lower, (
                        f"Stage 30.8.1 module {filename!r} defines "
                        f"writer-like function {node.name!r}"
                    )


def test_no_writer_like_method_calls() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Call) and isinstance(
                node.func, ast.Attribute
            ):
                lower = node.func.attr.lower()
                for token in _WRITER_NAME_TOKENS:
                    assert token not in lower, (
                        f"Stage 30.8.1 module {filename!r} calls "
                        f"writer-like method {node.func.attr!r}"
                    )


def test_no_builtin_open_call() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Call) and isinstance(
                node.func, ast.Name
            ):
                assert node.func.id != "open", (
                    f"Stage 30.8.1 module {filename!r} calls builtin "
                    f"open()"
                )


# ---------------------------------------------------------------------------
# 9. Zero top-level Call nodes (no implicit I/O at import time)
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
            f"Stage 30.8.1 module {filename!r} must carry zero "
            f"top-level Call nodes; offenders: {hits!r}"
        )


# ---------------------------------------------------------------------------
# 10. No Stage 30.8.2+ file admitted by the manifest inventory
# ---------------------------------------------------------------------------


def test_manifest_inventory_admits_no_stage_30_8_2_plus_file() -> None:
    future_tokens = ("30_8_2", "30_8_3", "30_8_4")
    inventory = (
        tuple(STAGE30_8_1_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_8_1_TEST_BASENAMES)
    )
    for basename in inventory:
        for token in future_tokens:
            assert token not in basename, (
                "Stage 30.8.1 manifest inventory must not admit a Stage "
                f"30.8.2+ file yet; saw {basename!r}"
            )
