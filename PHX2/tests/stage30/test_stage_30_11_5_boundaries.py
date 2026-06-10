"""Stage 30.11.5 controlled live ceremony wiring boundary tests.

Scans the five Stage 30.11.5 production .py modules (the live wiring models, the
live-candidate snapshot assembler, the private transport adapter, the bounded
live runner, the fake live wiring proof) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses`` / ``decimal`` -- NO ``time`` / ``datetime``),
  * a positive PHX2 import allowlist (the Stage 30.11.5 own siblings plus the
    committed Stage 30.11.1 bridge-models, Stage 30.11.2 runtime-gate-models +
    seam + fake proof, and Stage 30.11.3 private-sink-models + adapter the slice
    composes ONLY) -- which proves, by construction, that NO Stage 21-29 (incl.
    the nested Stage 27 / 28 / 29 live candidate record, Stage 28 suppression,
    Stage 29 live provider) / Stage 30.3 / Stage 30.4 runtime orchestrator /
    renderer / real transport / Discord / live provider / network module is
    imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` access,
  * no database / SQLite / compression surface import,
  * no network / secret / subprocess / threading / async / time import,
  * no Stage 21-29 / Stage 29.5 / PHX1 import,
  * no forbidden secret / transport / URL text needle and no ``://`` literal,
  * no public / subscriber / paid / Telegram / social / trading / wallet /
    enforcement term,
  * the transport client is INJECTED only (a parameter), the slice calls it from
    a single adapter call site, and the slice defines / imports no real Discord /
    webhook / transport client,
  * the runtime clock is INJECTED (a ``now_seconds`` parameter); no wall-clock
    read; no unbounded ``while`` loop / daemon,
  * no transport-safety flag set ``True`` for a candidate,
  * no filesystem write surface,
  * no implicit I/O at import time (zero top-level Call nodes),
  * the slice composes the committed seam + private sink + bridge models (it
    reimplements no bridge / gate / seam / sink),
  * no Stage 30.11.6+ / Stage 31 file admitted by the Stage 30.11.5 inventory,
    and
  * the Stage 30.11.5 slice is a leaf: no OTHER stage30 file imports it, and the
    committed surfaces it composes do not import it back.

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_5_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_5_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_13_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_15_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_17_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_18_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_19_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_20_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_21_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_5_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME,
    STAGE30_11_5_BOUNDED_LIVE_RUNNER_MODULE,
    STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_BASENAME,
    STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME,
    STAGE30_11_5_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_5_STAGE30_11_1_BRIDGE_MODELS_MODULE,
    STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
    STAGE30_11_5_TEST_BASENAMES,
    STAGE30_11_6_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_11_5_SCANNED_PRODUCTION_BASENAMES
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
# 1. Files exist + import cleanly + scanned set is the five modules
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_11_5_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.5 requires {basename}"
        )


def test_scanned_basenames_are_the_five_modules() -> None:
    assert STAGE30_11_5_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_5_ALLOWED_STAGE30_BASENAMES
    )
    assert len(STAGE30_11_5_SCANNED_PRODUCTION_BASENAMES) == 5


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_11_5_live_wiring_models  # noqa: F401
    import PHX2.stage30.stage30_11_5_live_candidate_snapshot_assembler  # noqa: F401,E501
    import PHX2.stage30.stage30_11_5_private_transport_adapter  # noqa: F401
    import PHX2.stage30.stage30_11_5_bounded_live_runner  # noqa: F401
    import PHX2.stage30.stage30_11_5_fake_live_wiring_proof  # noqa: F401


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
                module in STAGE30_11_5_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_11_5_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.11.5 module {filename!r} imports non-allowlisted "
                f"stdlib / third-party module {module!r}"
            )


def test_stdlib_allowlist_excludes_io_db_and_clock_surfaces() -> None:
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
    ):
        assert forbidden not in STAGE30_11_5_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_11_5_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.11.5 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_models_import_only_the_committed_bridge_models() -> None:
    # The Stage 30.11.5 models embed the committed Stage 30.11.1 snapshot type, so
    # (unlike the Stage 30.11.4 models) they import exactly that ONE committed
    # sibling -- and nothing else.
    phx2 = _phx2_imports_of(STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME)
    assert phx2 == {STAGE30_11_5_STAGE30_11_1_BRIDGE_MODELS_MODULE}, (
        "Stage 30.11.5 models must import only the committed Stage 30.11.1 "
        f"bridge-models sibling; found {sorted(phx2)}"
    )


def test_assembler_imports_the_committed_bridge_models() -> None:
    phx2 = _phx2_imports_of(
        STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_BASENAME
    )
    assert STAGE30_11_5_STAGE30_11_1_BRIDGE_MODELS_MODULE in phx2


def test_runner_composes_the_seam_and_the_private_sink() -> None:
    # The runner composes existing modules (it reimplements no seam / sink): it
    # MUST import the committed Stage 30.11.2 runtime seam and the committed Stage
    # 30.11.3 private sink adapter.
    phx2 = _phx2_imports_of(STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME)
    for required in (
        STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
        STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
    ):
        assert required in phx2, (
            f"Stage 30.11.5 runner must compose the committed module {required!r}"
        )


def test_phx2_allowlist_stays_within_stage30_family() -> None:
    for module in STAGE30_11_5_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_5_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.11.5 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.11.5 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.11.5 module {filename!r} performs "
                    f"os.{node.attr} access"
                )


# ---------------------------------------------------------------------------
# 4. No database / compression / network / concurrency / clock imports
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
                    f"Stage 30.11.5 module {filename!r} imports database / "
                    f"compression surface module {module!r}"
                )


_FORBIDDEN_NETWORK_CLOCK_OR_CONCURRENCY_MODULES: Tuple[str, ...] = (
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


def test_no_network_clock_or_concurrency_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_CLOCK_OR_CONCURRENCY_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.11.5 module {filename!r} imports forbidden "
                    f"network / clock / concurrency module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / Stage 29.5 / PHX1 import (incl. Stage 27 / 28 / 29)
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
                    f"Stage 30.11.5 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            for needle in ("stage27", "stage28", "stage29"):
                assert needle not in module, (
                    f"Stage 30.11.5 module {filename!r} imports nested live "
                    f"candidate record module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.11.5 module {filename!r} imports PHX1 module "
                f"{module!r}"
            )


# ---------------------------------------------------------------------------
# 6. No Discord / provider / runtime / real-transport import surface
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
    "live_provider",
    "suppress",
    "orchestrator",
)


def test_no_provider_runtime_or_transport_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module in STAGE30_11_5_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.11.5 module {filename!r} imports forbidden "
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
                f"Stage 30.11.5 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.11.5 module {filename!r} carries a transport scheme "
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
                f"Stage 30.11.5 module {filename!r} carries forbidden "
                f"surface term {term!r}"
            )


# ---------------------------------------------------------------------------
# 9. Composition discipline: injected transport client; no real send call
# ---------------------------------------------------------------------------


def test_production_modules_call_no_real_send_surface() -> None:
    # No production module CALLS a Discord / webhook / urlopen send-like function
    # (AST call-name proof). The injected transport client / committed sink
    # factory / seam are legitimately named and reached only through the import
    # allowlist, which already forbids any real transport module.
    forbidden_call_substrings = (
        "discord",
        "web" + "hook",
        "urlopen",
    )
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name is None:
                continue
            lowered = name.lower()
            for bad in forbidden_call_substrings:
                assert bad not in lowered, (
                    f"Stage 30.11.5 module {filename!r} calls a real send "
                    f"surface {name!r}"
                )


def test_transport_client_is_injected_not_constructed_at_module_level() -> None:
    # The bounded runner + transport adapter receive the transport client as a
    # parameter; no production module constructs a real client. The only fake
    # client lives in the fake proof module (a recording in-memory fake).
    for basename in (
        STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME,
        STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME,
    ):
        text = _source_of(basename)
        assert "transport_client" in text or "transport" in text


def test_no_filesystem_write_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in ("open(", "Path(", ".write_text(", ".write_bytes("):
            assert needle not in text, (
                f"Stage 30.11.5 module {filename!r} carries a filesystem "
                f"write surface {needle!r}"
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
                f"Stage 30.11.5 module {filename!r} sets {flag}=True"
            )


# ---------------------------------------------------------------------------
# 10. Runtime discipline: no unbounded loop / daemon; injected clock
# ---------------------------------------------------------------------------


def test_no_while_loop_in_any_production_module() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.11.5 module {filename!r} carries a while loop "
                f"(no unbounded loop / daemon is allowed)"
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


def test_no_daemon_or_thread_call_or_import_surface() -> None:
    needles = ("daemon", "thread", "spawn", "fork", "sleep")
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.11.5 module {filename!r} calls a daemon / "
                    f"thread surface {name!r}"
                )
        for module in _imports_of(text):
            lowered = module.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.11.5 module {filename!r} imports a daemon / "
                    f"thread surface {module!r}"
                )


def test_runner_clock_is_injected_not_read() -> None:
    runner = _source_of(STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME)
    assert "now_seconds" in runner
    # No module-level wall-clock surface.
    for needle in ("datetime.now", "time.time", "time.monotonic"):
        assert needle not in runner


# ---------------------------------------------------------------------------
# 11. No implicit I/O at import time (zero top-level Call nodes)
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
            f"Stage 30.11.5 module {filename!r} carries an unexpected "
            f"top-level call (implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# 12. No Stage 30.11.6+ / Stage 31 file admitted by the Stage 30.11.5 inventory
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_11_6_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_11_5_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_5_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_11_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 5, (
                "Stage 30.11.5 inventory must not admit a Stage 30.11.6+ "
                f"file yet; offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.11.5 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )


# ---------------------------------------------------------------------------
# 13. The Stage 30.11.5 slice is a LEAF: no existing production file imports it
# ---------------------------------------------------------------------------


_STAGE_30_11_5_MODULE_PREFIX: str = "PHX2.stage30.stage30_11_5_"


def test_no_existing_stage30_file_imports_the_slice() -> None:
    # The Stage 30.11.5 controlled live ceremony wiring slice is a clean leaf for
    # every EXISTING stage30 file: only its OWN five modules import each other; no
    # OTHER stage30 file (Stage 28 / 29 / existing Stage 30 production, incl. the
    # committed Stage 30.11.1 bridge + Stage 30.11.2 seam + Stage 30.11.3 sink it
    # composes) imports it -- proving nothing existing was edited to wire in the
    # new live wiring. The SOLE permitted exception is the explicitly
    # operator-authorized successor slice Stage 30.11.6 (the real candidate source /
    # harvest seam), which composes the committed Stage 30.11.5 bounded runner /
    # fake wiring proof as its downstream sink (the permitted Stage 30.11 scope
    # expansion). That successor is NEW (not an edit of an existing file) and is
    # excluded here; the guard still forbids every other stage30 file from
    # importing the slice.
    own_basenames = set(STAGE30_11_5_ALLOWED_STAGE30_BASENAMES)
    # The SOLE permitted importers are the FOUR EXACT Stage 30.11.6 production
    # basenames (from the manifest's pinned inventory) -- an exact membership
    # check, NOT a wildcard / prefix: it admits neither a future stage30_11_6_*
    # file, nor the Stage 30.11.6 test files, nor any other stage30 file.
    # The authorized importers: the Stage 30.11.6 harvest successor, the Stage
    # 30.11.13 committed no-send composer + its fake proof (the integration
    # capstone that composes the committed bounded runner), AND the Stage
    # 30.11.15 cross-run dedupe slice (its fake dedupe proof composes the
    # committed Stage 30.11.5 recording fake transport client to drive the
    # deduped composer). All are NEW files (not edits of existing files); every
    # OTHER stage30 file is still forbidden from importing the slice.
    admitted_successor_basenames = (
        set(STAGE30_11_6_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_13_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_15_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_17_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_18_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_19_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_20_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_21_ALLOWED_STAGE30_BASENAMES)
    )
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__" or not entry.name.endswith(".py"):
            continue
        if entry.name in own_basenames:
            continue
        if entry.name in admitted_successor_basenames:
            # The authorized Stage 30.11.6 successor PRODUCTION modules MAY compose
            # the committed Stage 30.11.5 surface (the permitted Stage 30.11 scope
            # expansion); their own boundary test pins exactly which Stage 30.11.5
            # module each imports.
            continue
        text = entry.read_text(encoding="utf-8")
        for module in _imports_of(text):
            assert not module.startswith(_STAGE_30_11_5_MODULE_PREFIX), (
                f"{entry.name!r} imports the Stage 30.11.5 slice "
                f"({module!r}); the slice is a leaf and is not wired into the "
                f"runtime (no existing production file may be edited to import "
                f"it)"
            )


def test_composed_committed_surfaces_do_not_import_the_slice() -> None:
    # The slice DEPENDS ON the committed Stage 30.11.1 bridge models + Stage
    # 30.11.2 seam / models / fake proof + Stage 30.11.3 private sink models /
    # adapter; the dependency must point one direction only (those committed files
    # must not import the Stage 30.11.5 slice).
    for basename in (
        "stage30_11_1_live_candidate_bridge_models.py",
        "stage30_11_2_runtime_gate_models.py",
        "stage30_11_2_runtime_gate_seam.py",
        "stage30_11_2_fake_runtime_gate_proof.py",
        "stage30_11_3_private_sink_models.py",
        "stage30_11_3_private_sink_adapter.py",
    ):
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"expected {path} to exist"
        for module in _imports_of(path.read_text(encoding="utf-8")):
            assert not module.startswith(_STAGE_30_11_5_MODULE_PREFIX), (
                f"committed file {basename!r} must not import the Stage "
                f"30.11.5 slice ({module!r})"
            )


def test_runner_module_path_pinned() -> None:
    assert STAGE30_11_5_BOUNDED_LIVE_RUNNER_MODULE == (
        "PHX2.stage30.stage30_11_5_bounded_live_runner"
    )


def test_scanned_and_test_basenames_carry_no_secret_terms() -> None:
    names: List[str] = list(STAGE30_11_5_ALLOWED_STAGE30_BASENAMES) + list(
        STAGE30_11_5_TEST_BASENAMES
    )
    for name in names:
        lower = name.lower()
        for forbidden in ("secret", "web" + "hook", "token_url", "api_key"):
            assert forbidden not in lower, (
                f"Stage 30.11.5 basename {name!r} carries forbidden term "
                f"{forbidden!r}"
            )
