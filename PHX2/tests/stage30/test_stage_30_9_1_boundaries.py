"""Stage 30.9.1 production-file boundary tests.

Scans the four Stage 30.9.1 production .py modules (the passive bridge
models + the capture transport + the projector + the bridge proof) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses``; only the models module needs ``dataclasses`` -- the
    capture transport / projector / proof need only ``typing``, since the
    JSON / pathlib I/O lives behind the composed Stage 30.8.2 writer +
    Stage 30.8.3 reader / builder),
  * a positive PHX2 import allowlist (the bridge models import NO PHX2
    module; the capture transport imports only the bridge-models sibling;
    the projector imports the bridge-models + Stage 30.8.1 models + Stage
    30.8.2 writer; the proof imports the bridge-models + projector + Stage
    30.8.1 models + Stage 30.8.2 writer + Stage 30.8.3 reader /
    index-builder / index-models) -- which proves, by construction, that NO
    Stage 21-29 (incl. Stage 28 / Stage 29.5) / runtime / orchestrator /
    renderer / Discord / provider / network module is imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` access,
  * no database / SQLite / compression surface import,
  * no network / secret / subprocess / threading / async module import,
  * no ``time`` import and no ``sleep`` call,
  * no Stage 21-29 / Stage 29.5 / PHX1 import,
  * no Discord / provider / runtime / renderer import surface,
  * no forbidden secret / transport / URL text needles (no real webhook
    string literal, no transport scheme),
  * no public / subscriber / paid / Telegram / social / trading / wallet /
    enforcement term (those live only in the manifest forbidden-surface
    constants / the tests),
  * zero top-level Call nodes (no implicit I/O at import time),
  * the capture transport / projector / proof carry NO direct filesystem
    write / open primitive (every write goes through the Stage 30.8.2
    writer, every read through the Stage 30.8.3 reader / builder),
  * no Stage 30.9.2+ file admitted by the manifest inventory,
  * no Stage 30.8 / runtime / renderer file imports the Stage 30.9.1 slice
    (the bridge is a leaf; nothing existing depends on it).

Fake / offline only. No live call, no actual collection root, no Discord.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_9_manifest import (
    STAGE30_9_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_9_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_9_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME,
    STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE,
    STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME,
    STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME,
    STAGE30_9_1_ARTIFACT_PROJECTOR_MODULE,
    STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME,
    STAGE30_9_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_9_1_TEST_BASENAMES,
    STAGE30_9_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scanned_sources() -> Dict[str, str]:
    files: Dict[str, str] = {}
    for basename in STAGE30_9_1_SCANNED_PRODUCTION_BASENAMES:
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


def _phx2_imports_of(basename: str) -> Set[str]:
    return {m for m in _imports_of(_source_of(basename)) if m.startswith("PHX2.")}


# ---------------------------------------------------------------------------
# 1. Files exist + import cleanly
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_9_1_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.9.1 requires {basename}"
        )


def test_scanned_basenames_are_the_four_modules() -> None:
    assert STAGE30_9_1_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME,
        STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME,
        STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME,
        STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME,
    )


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_9_artifact_bridge_models  # noqa: F401
    import PHX2.stage30.stage30_9_capture_transport  # noqa: F401
    import PHX2.stage30.stage30_9_artifact_projector  # noqa: F401
    import PHX2.stage30.stage30_9_artifact_bridge_proof  # noqa: F401


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
                module in STAGE30_9_1_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_9_1_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.9.1 module {filename!r} imports "
                f"non-allowlisted stdlib/3rd-party module {module!r}"
            )


def test_models_import_no_phx2_module() -> None:
    phx2 = _phx2_imports_of(STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME)
    assert phx2 == set(), (
        "Stage 30.9.1 bridge models must import no PHX2 module; found "
        f"{sorted(phx2)}"
    )


def test_models_module_is_filesystem_free() -> None:
    imports = _imports_of(
        _source_of(STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME)
    )
    for module in imports:
        top = module.split(".")[0]
        assert top in ("__future__", "typing", "dataclasses"), (
            "Stage 30.9.1 bridge models must import only __future__ / "
            f"typing / dataclasses; saw {module!r}"
        )


def test_capture_transport_phx2_imports_are_exactly_the_bridge_models() -> None:
    phx2 = _phx2_imports_of(STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME)
    assert phx2 == {STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE}, (
        "Stage 30.9.1 capture transport must import only the bridge-models "
        f"sibling; found {sorted(phx2)}"
    )


def test_projector_phx2_imports_are_exactly_the_allowlist() -> None:
    phx2 = _phx2_imports_of(STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME)
    assert phx2 == {
        STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE,
        "PHX2.stage30.stage30_8_artifact_models",
        "PHX2.stage30.stage30_8_temp_artifact_writer",
    }, (
        "Stage 30.9.1 projector must import only the bridge-models + Stage "
        f"30.8.1 models + Stage 30.8.2 writer siblings; found {sorted(phx2)}"
    )


def test_proof_phx2_imports_are_exactly_the_allowlist() -> None:
    phx2 = _phx2_imports_of(STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME)
    assert phx2 == {
        STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE,
        STAGE30_9_1_ARTIFACT_PROJECTOR_MODULE,
        "PHX2.stage30.stage30_8_artifact_models",
        "PHX2.stage30.stage30_8_temp_artifact_writer",
        "PHX2.stage30.stage30_8_session_bundle_reader",
        "PHX2.stage30.stage30_8_session_index_builder",
        "PHX2.stage30.stage30_8_session_index_models",
    }, (
        "Stage 30.9.1 proof must import only the bridge-models + projector "
        "+ Stage 30.8.1 models + Stage 30.8.2 writer + Stage 30.8.3 reader "
        f"/ index-builder / index-models siblings; found {sorted(phx2)}"
    )


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_9_1_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.9.1 module {filename!r} imports "
                f"non-allowlisted PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_stage_30_siblings_only() -> None:
    for module in STAGE30_9_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.9.1 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.9.1 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        tree = _module_ast(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.9.1 module {filename!r} performs "
                    f"os.{node.attr} access"
                )


# ---------------------------------------------------------------------------
# 4. No database / compression / network / secret / concurrency imports
# ---------------------------------------------------------------------------


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
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.9.1 module {filename!r} imports database / "
                    f"compression surface module {module!r}"
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
)


def test_no_network_secret_or_concurrency_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_OR_CONCURRENCY_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.9.1 module {filename!r} imports forbidden "
                    f"network / secret / concurrency module {module!r}"
                )


def test_no_sleep_call_surface() -> None:
    # No wall-clock daemon / sleep: no ``time.sleep`` / bare ``sleep(``
    # CALL token in any production module (the word "sleep" may appear in a
    # docstring naming the forbidden surface; a call site may not).
    for filename, text in _scanned_sources().items():
        assert "sleep(" not in text, (
            f"Stage 30.9.1 module {filename!r} carries a sleep call surface"
        )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / Stage 29.5 / PHX1 import (incl. Stage 28)
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
                    f"Stage 30.9.1 module {filename!r} imports Stage "
                    f"21-29 module {module!r}"
                )
            assert "stage28" not in module, (
                f"Stage 30.9.1 module {filename!r} imports Stage 28 "
                f"module {module!r}"
            )
            assert "stage29" not in module, (
                f"Stage 30.9.1 module {filename!r} imports Stage 29 / "
                f"29.5 module {module!r}"
            )
            assert not module.startswith("PHX1"), (
                f"Stage 30.9.1 module {filename!r} imports PHX1 "
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
    "live_provider",
    "compact_ping",
)


def test_no_provider_runtime_or_renderer_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module in STAGE30_9_1_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.9.1 module {filename!r} imports forbidden "
                    f"surface {needle!r}; offender {module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden secret / transport / URL text needles
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_9_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.9.1 module {filename!r} carries forbidden "
                f"text needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    # Defence in depth: no transport scheme prefix appears as a literal.
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.9.1 module {filename!r} carries a transport scheme "
            f"literal"
        )


# ---------------------------------------------------------------------------
# 8. No public / subscriber / paid / social / trading / wallet /
#    enforcement term (those live only in the manifest constants / tests)
# ---------------------------------------------------------------------------


_FORBIDDEN_SURFACE_TERMS: Tuple[str, ...] = (
    "public routing",
    "subscriber",
    "paid tier",
    "telegram",
    "x / social",
    "automated trading",
    "auto-buy",
    "auto buy",
    "wallet",
    "private_key",
    "signing material",
    "enforcement",
)


def test_no_forbidden_surface_terms_in_production_modules() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for term in _FORBIDDEN_SURFACE_TERMS:
            assert term not in lower, (
                f"Stage 30.9.1 module {filename!r} carries forbidden "
                f"surface term {term!r}"
            )


# ---------------------------------------------------------------------------
# 9. Zero top-level Call nodes (no implicit I/O at import time)
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
            f"Stage 30.9.1 module {filename!r} must carry zero top-level "
            f"Call nodes; offenders: {hits!r}"
        )


# ---------------------------------------------------------------------------
# 10. The capture transport / projector / proof carry no direct filesystem
#     write / open primitive
# ---------------------------------------------------------------------------


_DIRECT_IO_TOKENS: Tuple[str, ...] = (
    "write_text",
    "write_bytes",
    "mkdir",
    ".rename(",
    ".replace(",
    ".unlink(",
    ".rmdir(",
    ".touch(",
    "open(",
    "Path(",
)


def test_modules_carry_no_direct_filesystem_io() -> None:
    for filename, text in _scanned_sources().items():
        for token in _DIRECT_IO_TOKENS:
            assert token not in text, (
                f"Stage 30.9.1 module {filename!r} carries a direct "
                f"filesystem primitive {token!r}; the bridge must delegate "
                f"all I/O to the Stage 30.8.2 writer / Stage 30.8.3 reader"
            )


# ---------------------------------------------------------------------------
# 11. No Stage 30.9.2+ file admitted by the manifest inventory
# ---------------------------------------------------------------------------


_STAGE_30_9_MINOR_RE = re.compile(r"stage_?30_9_(\d+)")


def test_manifest_inventory_admits_no_stage_30_9_2_plus_file() -> None:
    inventory = (
        tuple(STAGE30_9_1_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_9_1_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_9_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 2:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.9.1 manifest inventory must not admit a Stage 30.9.2+ "
        f"file yet; saw {violations!r}"
    )


# ---------------------------------------------------------------------------
# 12. No Stage 30.8 / runtime / renderer file imports the Stage 30.9.1 slice
# ---------------------------------------------------------------------------
#
# The Stage 30.9.1 bridge is a LEAF: it composes the existing Stage 30.8
# storage chain, and nothing existing depends on it. The runtime
# orchestrators + compact renderer / models + the Stage 30.8.1 / 30.8.2 /
# 30.8.3 / 30.8.4 production modules must not reference the Stage 30.9.1
# bridge modules.


_FILES_THAT_MUST_NOT_IMPORT_THE_BRIDGE: Tuple[str, ...] = (
    "stage30_4_compact_runtime_session_orchestrator.py",
    "stage30_3_compact_runtime_session_orchestrator.py",
    "compact_ping_renderer.py",
    "compact_ping_models.py",
    "stage30_8_artifact_models.py",
    "stage30_8_artifact_validators.py",
    "stage30_8_temp_artifact_writer.py",
    "stage30_8_session_index_models.py",
    "stage30_8_session_bundle_reader.py",
    "stage30_8_session_index_builder.py",
    "stage30_8_controlled_artifact_proof.py",
    "stage30_8_controlled_artifact_proof_models.py",
)


def test_existing_files_do_not_import_the_bridge() -> None:
    # "stage30_9_" is the shared prefix of all four Stage 30.9.1 bridge
    # module basenames, so this single needle catches a reference to any of
    # them (the only existing ``stage30_9_*`` file is the manifest, which
    # the list below does not include).
    needle = "stage30_9_"
    for basename in _FILES_THAT_MUST_NOT_IMPORT_THE_BRIDGE:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"expected {path} to exist"
        text = path.read_text(encoding="utf-8")
        assert needle not in text, (
            f"{basename!r} must not reference a Stage 30.9.1 bridge "
            f"module ({needle!r}); the bridge is a leaf"
        )
