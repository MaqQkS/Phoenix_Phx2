"""Stage 30.7.4 closure-slice boundary tests.

Stage 30.7.4 is a CLOSURE AUDIT + HANDOFF slice. It ships two markdown
documents + one constants-only manifest + four test modules, and adds
ZERO runtime production code. This boundary suite proves exactly that:

  * the only NEW production .py the closure slice adds is the
    constants-only ``stage30_7_4_manifest.py`` (no runtime module),
  * that manifest is constants-only (no def / class / Call) and imports
    only ``__future__`` + ``typing`` -- so it reaches NO os / network /
    disk / database / compression / provider / Discord / Stage 21-29 /
    Stage 30 runtime surface,
  * the manifest carries no forbidden secret / host / transport text
    needle (the Stage 30.7.0 split-literal needle vocabulary),
  * the compact renderer / compact models / Stage 30.4.2 orchestrator
    carry NO Stage 30.7.4 wiring (the closure slice did not edit them),
  * the closure inventory admits NO Stage 30.7.5+ file.

Doc / constants only. No live call, no provider, no Discord, no env
read, no DB, no zstd, no enforcement.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_7_4_manifest import (
    STAGE30_7_4_ALLOWED_STDLIB_IMPORTS,
    STAGE30_7_4_MANIFEST_BASENAME,
    STAGE30_7_4_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_7_4_TEST_BASENAMES,
    STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4,
)
from PHX2.stage30.stage30_7_manifest import (
    STAGE30_7_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"

_RENDERER_BASENAME: str = "compact_ping_renderer.py"
_MODELS_BASENAME: str = "compact_ping_models.py"
_ORCHESTRATOR_BASENAME: str = (
    "stage30_4_compact_runtime_session_orchestrator.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scanned_sources() -> Dict[str, str]:
    files: Dict[str, str] = {}
    for basename in STAGE30_7_4_SCANNED_PRODUCTION_BASENAMES:
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
# 1. Closure files exist + only the manifest is a new production .py
# ---------------------------------------------------------------------------


def test_closure_files_exist() -> None:
    for basename in STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.7.4 requires {basename}"
        )


def test_only_new_stage30_7_4_production_file_is_the_manifest() -> None:
    """The closure slice adds NO runtime code: the only NEW production
    entry whose basename starts with ``stage30_7_4`` is the constants-
    only manifest. (The two closure docs are markdown.)
    """
    stage30_7_4_entries = {
        entry.name
        for entry in STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and entry.name.startswith("stage30_7_4")
    }
    assert stage30_7_4_entries == {STAGE30_7_4_MANIFEST_BASENAME}, (
        "Stage 30.7.4 must add only the constants-only manifest as a "
        f"stage30_7_4 production file; found {sorted(stage30_7_4_entries)}"
    )


def test_closure_inventory_is_two_docs_plus_one_manifest() -> None:
    # Exactly two markdown docs + exactly one .py (the manifest).
    md_files = [
        b
        for b in STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4
        if b.endswith(".md")
    ]
    py_files = [
        b
        for b in STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4
        if b.endswith(".py")
    ]
    assert len(md_files) == 2, f"expected 2 closure docs, got {md_files}"
    assert py_files == [STAGE30_7_4_MANIFEST_BASENAME], (
        f"expected exactly the manifest .py, got {py_files}"
    )


def test_manifest_imports_cleanly() -> None:
    import PHX2.stage30.stage30_7_4_manifest  # noqa: F401


# ---------------------------------------------------------------------------
# 2. The manifest is constants-only + stdlib-only imports
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only_no_def_class_call() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ), f"{filename!r} must be constants-only (no def/class)"
            assert not isinstance(node, ast.Call), (
                f"{filename!r} must be constants-only (no Call)"
            )


def test_manifest_non_phx2_imports_in_stdlib_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            top = module.split(".")[0]
            assert (
                module in STAGE30_7_4_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_7_4_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.7.4 {filename!r} imports non-allowlisted "
                f"stdlib / 3rd-party module {module!r}"
            )


def test_manifest_imports_no_phx2_module() -> None:
    # The closure manifest is pure constants: it imports NO PHX2 module
    # (so it reaches no Stage 30 runtime / Stage 21-29 production surface).
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            assert not module.startswith("PHX2."), (
                f"Stage 30.7.4 {filename!r} must import no PHX2 module; "
                f"offender {module!r}"
            )


# ---------------------------------------------------------------------------
# 3. No os / network / disk / database / compression module imports
# ---------------------------------------------------------------------------


_FORBIDDEN_MODULES: Tuple[str, ...] = (
    "os",
    "pathlib",
    "shutil",
    "sqlite3",
    "zstandard",
    "zstd",
    "lzma",
    "gzip",
    "zlib",
    "urllib",
    "socket",
    "grpc",
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


def test_manifest_imports_no_forbidden_surface_module() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.7.4 {filename!r} imports forbidden "
                    f"surface module {module!r}"
                )


def test_manifest_imports_no_stage21_29_or_phx1() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for stage_n in range(21, 30):
                prefix = f"PHX2.stage{stage_n}"
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.7.4 {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.7.4 {filename!r} imports PHX1 module {module!r}"
            )


# ---------------------------------------------------------------------------
# 4. No forbidden secret / host / transport text needles in production
# ---------------------------------------------------------------------------


def test_manifest_carries_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_7_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.7.4 {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_manifest_carries_no_transport_or_filesystem_needles() -> None:
    needles = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "requests." + "post",
        "ses" + "sion.post",
        "url" + "open",
        "send_one_audited_post",
        "open(",
        ".write_" + "text",
        ".write_" + "bytes",
        "pathlib.",
        "sqlite3.",
    )
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in needles:
            assert needle.lower() not in lower, (
                f"Stage 30.7.4 {filename!r} carries forbidden "
                f"transport / filesystem needle {needle!r}"
            )


def test_manifest_no_builtin_open_call() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Call) and isinstance(
                node.func, ast.Name
            ):
                assert node.func.id != "open", (
                    f"Stage 30.7.4 {filename!r} calls builtin open()"
                )


# ---------------------------------------------------------------------------
# 5. Renderer / compact models / orchestrator NOT edited by Stage 30.7.4
# ---------------------------------------------------------------------------


_STAGE30_7_4_WIRING_NEEDLES: Tuple[str, ...] = (
    "stage30_7_4",
    "STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT",
    "STAGE_30_7_ATH_CONTEXT_HANDOFF",
    "closure_audit",
)


def test_renderer_and_models_carry_no_stage30_7_4_wiring() -> None:
    for basename in (_RENDERER_BASENAME, _MODELS_BASENAME):
        text = (STAGE30_ROOT / basename).read_text(encoding="utf-8")
        for needle in _STAGE30_7_4_WIRING_NEEDLES:
            assert needle not in text, (
                f"Stage 30.7.4 must not wire into {basename!r}; "
                f"found {needle!r}"
            )


def test_orchestrator_not_edited_by_stage30_7_4() -> None:
    """The closure slice adds no reference to itself in the Stage 30.4.2
    orchestrator, and the orchestrator still imports no Stage 30.7 module
    (the Stage 30.7.2 ``ath_context_resolver`` seam is duck-typed). The
    pre-existing 30.7.2 seam tokens are not a 30.7.4 edit.
    """
    text = (STAGE30_ROOT / _ORCHESTRATOR_BASENAME).read_text(
        encoding="utf-8"
    )
    for needle in _STAGE30_7_4_WIRING_NEEDLES:
        assert needle not in text, (
            f"Stage 30.7.4 must not edit the orchestrator; found "
            f"{needle!r}"
        )
    for module in _imports_of(text):
        assert not module.startswith("PHX2.stage30.stage30_7"), (
            "Stage 30.4.2 orchestrator must still import no Stage 30.7 "
            f"module; offender {module!r}"
        )


# ---------------------------------------------------------------------------
# 6. The closure inventory admits no Stage 30.7.5+ file
# ---------------------------------------------------------------------------


def test_closure_admits_no_stage_30_7_5_file() -> None:
    for basename in (
        STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4
        + STAGE30_7_4_SCANNED_PRODUCTION_BASENAMES
        + STAGE30_7_4_TEST_BASENAMES
    ):
        assert "7_5" not in basename, (
            f"Stage 30.7.4 must not admit a Stage 30.7.5+ file; offender "
            f"{basename!r}"
        )
    # No actual Stage 30.7.5 production / test file exists yet.
    stage30_7_5_prod = [
        entry.name
        for entry in STAGE30_ROOT.iterdir()
        if entry.name.startswith("stage30_7_5")
        or entry.name.startswith("STAGE_30_7_5")
    ]
    assert stage30_7_5_prod == [], (
        f"no Stage 30.7.5 production file may exist yet; found "
        f"{stage30_7_5_prod}"
    )
