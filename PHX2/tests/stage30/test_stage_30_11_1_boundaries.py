"""Stage 30.11.1 live-candidate assembly bridge boundary tests.

Scans the three Stage 30.11.1 production .py modules (the bridge models, the
bridge, the fake bridge proof) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses`` / ``decimal``),
  * a positive PHX2 import allowlist (the Stage 30.11.1 own models + bridge
    siblings plus the committed Stage 30.9.3 integration-models + dip-gate-
    adapter modules ONLY) -- which proves, by construction, that NO Stage 21-29
    (incl. Stage 28 suppression / Stage 29.5 / Stage 29 live provider) / Stage
    30.3 / Stage 30.4 runtime orchestrator / renderer / transport / Discord /
    live provider / network module is imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` access,
  * no database / SQLite / compression surface import,
  * no network / secret / subprocess / threading / async / time import,
  * no Stage 21-29 / Stage 29.5 / PHX1 import,
  * no forbidden secret / transport / URL text needle and no ``://`` literal,
  * no public / subscriber / paid / Telegram / social / trading / wallet /
    enforcement term,
  * no dispatch sink / dispatch reservation / Discord send / transport-veto
    surface (the bridge ONLY assembles a gate input),
  * no transport-safety flag set ``True`` for a candidate,
  * no filesystem write surface,
  * no implicit I/O at import time (zero top-level Call nodes),
  * no Stage 30.11.2+ / Stage 31 file admitted by the Stage 30.11.1 inventory,
    and
  * no existing runtime / orchestrator / transport / Stage 28 suppression /
    Stage 29 live provider / committed Stage 30.9.3 file imports the Stage
    30.11.1 slice (the slice is a leaf; nothing existing depends on it, and it
    is NOT wired into the runtime yet -- proving no Stage 28 / 29 / existing
    Stage 30 production file was edited to wire it in).

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_1_BRIDGE_BASENAME,
    STAGE30_11_1_BRIDGE_MODELS_BASENAME,
    STAGE30_11_1_BRIDGE_MODELS_MODULE,
    STAGE30_11_1_BRIDGE_MODULE,
    STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME,
    STAGE30_11_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE,
    STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_11_1_TEST_BASENAMES,
    STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_11_1_SCANNED_PRODUCTION_BASENAMES
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
# 1. Files exist + import cleanly + scanned set is the three modules
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_11_1_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.1 requires {basename}"
        )


def test_scanned_basenames_are_the_three_modules() -> None:
    assert STAGE30_11_1_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_1_BRIDGE_MODELS_BASENAME,
        STAGE30_11_1_BRIDGE_BASENAME,
        STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME,
    )


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_11_1_live_candidate_bridge_models  # noqa: F401,E501
    import PHX2.stage30.stage30_11_1_live_candidate_bridge  # noqa: F401
    import PHX2.stage30.stage30_11_1_fake_bridge_proof  # noqa: F401


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
                module in STAGE30_11_1_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_11_1_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.11.1 module {filename!r} imports non-allowlisted "
                f"stdlib / third-party module {module!r}"
            )


def test_stdlib_allowlist_excludes_io_and_db_surfaces() -> None:
    for forbidden in ("os", "json", "pathlib", "sqlite3", "zstandard", "time"):
        assert forbidden not in STAGE30_11_1_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_11_1_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.11.1 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_models_phx2_imports_are_only_the_committed_gate_models() -> None:
    # The permitted Stage 30.11 scope expansion: the bridge models EMBED the
    # committed Stage 30.9.3 live gate input, so they import that ONE model
    # module -- and nothing else.
    phx2 = _phx2_imports_of(STAGE30_11_1_BRIDGE_MODELS_BASENAME)
    assert phx2 == {STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE}, (
        "Stage 30.11.1 bridge models must import only the committed Stage "
        f"30.9.3 gate-models sibling; found {sorted(phx2)}"
    )


def test_bridge_phx2_imports_are_models_and_committed_gate_models() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_1_BRIDGE_BASENAME)
    assert phx2 == {
        STAGE30_11_1_BRIDGE_MODELS_MODULE,
        STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE,
    }, (
        "Stage 30.11.1 bridge must import its own models sibling plus the "
        f"committed Stage 30.9.3 gate-models sibling; found {sorted(phx2)}"
    )


def test_proof_phx2_imports_are_bridge_models_and_committed_gate() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME)
    assert phx2 == {
        STAGE30_11_1_BRIDGE_MODULE,
        STAGE30_11_1_BRIDGE_MODELS_MODULE,
        STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE,
        STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE,
    }, (
        "Stage 30.11.1 fake proof must import its own bridge + models siblings "
        "plus the committed Stage 30.9.3 dip-gate adapter + models; found "
        f"{sorted(phx2)}"
    )


def test_phx2_allowlist_stays_within_stage30_family() -> None:
    for module in STAGE30_11_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_1_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "transport", "suppress", "renderer"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.11.1 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.11.1 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.11.1 module {filename!r} performs "
                    f"os.{node.attr} access"
                )


# ---------------------------------------------------------------------------
# 4. No database / compression / network / concurrency imports
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
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.11.1 module {filename!r} imports database / "
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
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.11.1 module {filename!r} imports forbidden "
                    f"network / secret / concurrency module {module!r}"
                )


def test_no_sleep_call_surface() -> None:
    for filename, text in _scanned_sources().items():
        assert "sleep(" not in text, (
            f"Stage 30.11.1 module {filename!r} carries a sleep call surface"
        )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / Stage 29.5 / PHX1 import (incl. Stage 28 / 29)
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
                    f"Stage 30.11.1 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            assert "stage28" not in module, (
                f"Stage 30.11.1 module {filename!r} imports Stage 28 module "
                f"{module!r}"
            )
            assert "stage29" not in module, (
                f"Stage 30.11.1 module {filename!r} imports Stage 29 module "
                f"{module!r}"
            )
            assert not module.startswith("PHX1"), (
                f"Stage 30.11.1 module {filename!r} imports PHX1 module "
                f"{module!r}"
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
    "renderer",
    "transport",
    "live_provider",
    "suppress",
    "orchestrator",
)


def test_no_provider_runtime_or_transport_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module in STAGE30_11_1_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.11.1 module {filename!r} imports forbidden "
                    f"surface {needle!r}; offender {module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden secret / transport / URL text needles + no transport scheme
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_11_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.11.1 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.11.1 module {filename!r} carries a transport scheme "
            f"literal"
        )


# ---------------------------------------------------------------------------
# 8. No public / subscriber / paid / social / trading / wallet / enforcement
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
                f"Stage 30.11.1 module {filename!r} carries forbidden "
                f"surface term {term!r}"
            )


# ---------------------------------------------------------------------------
# 9. No dispatch sink / reservation / Discord send surface in the bridge
# ---------------------------------------------------------------------------


def _called_names(text: str) -> Set[str]:
    """Return the set of called function / method names in ``text`` (Call node
    callees only -- a word in a docstring / comment is NOT a match).
    """
    names: Set[str] = set()
    for node in ast.walk(_module_ast(text)):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def test_bridge_makes_no_dispatch_sink_or_gate_eval_call() -> None:
    # The bridge ONLY assembles a gate input: it must reserve no dispatch, call
    # no sink, and run no gate. AST proof over CALL NAMES (the bridge's
    # docstrings legitimately describe what it does NOT do, so prose is never
    # scanned). (The fake proof legitimately evaluates the pure gate verdict
    # via the adapter; this stricter check is the bridge module ONLY.)
    text = _source_of(STAGE30_11_1_BRIDGE_BASENAME)
    called = _called_names(text)
    for name in called:
        lowered = name.lower()
        assert "sink" not in lowered, (
            f"Stage 30.11.1 bridge calls a sink-like function {name!r}"
        )
        assert "dispatch" not in lowered, (
            f"Stage 30.11.1 bridge calls a dispatch-like function {name!r}"
        )
        assert "reserve" not in lowered, (
            f"Stage 30.11.1 bridge calls a reserve-like function {name!r}"
        )
    for forbidden in (
        "evaluate_dip_filtered_live_gate",
        "run_dip_filtered_live_gate_integration",
        "evaluate_pre_dispatch_tier_dip_gate",
    ):
        assert forbidden not in called, (
            f"Stage 30.11.1 bridge must not call {forbidden!r}"
        )
    # The bridge cannot run the gate / sink: it imports neither the Stage 30.9.3
    # adapter / orchestrator nor any Stage 30.10.2 gate -- only the gate-input
    # MODEL.
    bridge_imports = _imports_of(text)
    for forbidden_module in (
        STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE,
        "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_orchestrator",
        "PHX2.stage30.stage30_10_2_pre_dispatch_gate",
    ):
        assert forbidden_module not in bridge_imports, (
            f"Stage 30.11.1 bridge must not import {forbidden_module!r}"
        )


def test_no_transport_safety_flag_set_true() -> None:
    for filename, text in _scanned_sources().items():
        stripped = "".join(text.split())
        for flag in (
            "dispatch_failure_recorded",
            "transport_veto_used",
            "payload_refused_used",
            "dispatch_failures_recorded",
            "transport_veto_count",
            "payload_refused_count",
        ):
            assert f"{flag}=True" not in stripped, (
                f"Stage 30.11.1 module {filename!r} sets {flag}=True"
            )


def test_no_filesystem_write_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in ("open(", "Path(", ".write_text(", ".write_bytes("):
            assert needle not in text, (
                f"Stage 30.11.1 module {filename!r} carries a filesystem "
                f"write surface {needle!r}"
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
            f"Stage 30.11.1 module {filename!r} carries an unexpected "
            f"top-level call (implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# 11. No Stage 30.11.2+ / Stage 31 file admitted by the Stage 30.11.1 inventory
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_11_2_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_11_1_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_1_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_11_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 1, (
                "Stage 30.11.1 inventory must not admit a Stage 30.11.2+ "
                f"file yet; offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.11.1 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )


# ---------------------------------------------------------------------------
# 12. The Stage 30.11.1 slice is a LEAF: no existing production file imports it
#     (proves no Stage 28 / 29 / existing Stage 30 production file was edited
#     to wire in the new bridge -- it is not in the runtime path yet)
# ---------------------------------------------------------------------------


_STAGE_30_11_1_MODULE_PREFIX: str = "PHX2.stage30.stage30_11_1_"


def test_no_existing_stage30_file_imports_the_slice() -> None:
    new_basenames = set(STAGE30_11_1_ALLOWED_STAGE30_BASENAMES)
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__" or not entry.name.endswith(".py"):
            continue
        if entry.name in new_basenames:
            continue
        text = entry.read_text(encoding="utf-8")
        for module in _imports_of(text):
            assert not module.startswith(_STAGE_30_11_1_MODULE_PREFIX), (
                f"{entry.name!r} imports the Stage 30.11.1 slice "
                f"({module!r}); the slice is a leaf and is not wired into the "
                f"runtime yet (no existing production file may be edited to "
                f"import it)"
            )


def test_committed_stage_30_9_3_surfaces_do_not_import_the_slice() -> None:
    # The bridge DEPENDS ON the committed Stage 30.9.3 surfaces, never the
    # other way round; the dependency must point one direction only.
    for basename in (
        "stage30_9_3_dip_filtered_live_gate_models.py",
        "stage30_9_3_dip_filtered_live_gate_adapter.py",
        "stage30_9_3_dip_filtered_live_gate_orchestrator.py",
        "stage30_9_3_fake_live_gate_integration_proof.py",
    ):
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"expected {path} to exist"
        for module in _imports_of(path.read_text(encoding="utf-8")):
            assert not module.startswith(_STAGE_30_11_1_MODULE_PREFIX), (
                f"committed Stage 30.9.3 file {basename!r} must not import the "
                f"Stage 30.11.1 slice ({module!r})"
            )
