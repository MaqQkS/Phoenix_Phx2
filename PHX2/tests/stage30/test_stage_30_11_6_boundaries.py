"""Stage 30.11.6 real candidate source / harvest seam boundary tests.

Scans the four Stage 30.11.6 production .py modules (the candidate source models,
the harvested-candidate -> Stage 30.11.5 projection adapter, the candidate harvest
adapter, the fake candidate source proof) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses`` / ``decimal`` -- NO ``time`` / ``datetime``),
  * a positive PHX2 import allowlist (the Stage 30.11.6 own siblings plus the
    committed Stage 30.11.5 fake-live-wiring-proof the proof composes ONLY) --
    which proves, by construction, that NO Stage 21-29 (incl. the nested Stage 27 /
    28 / 29 live candidate record, the committed Stage 28.9 live provider session
    adapter, Stage 28 suppression, Stage 29 live provider) / Stage 30.3 / Stage
    30.4 runtime orchestrator / renderer / real transport / Discord / live provider
    / network module is imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` access,
  * no database / SQLite / compression surface import,
  * no network / secret / subprocess / threading / async / time import,
  * no Stage 21-29 / Stage 29.5 / PHX1 import,
  * no forbidden secret / transport / URL text needle and no ``://`` literal,
  * no public / subscriber / paid / Telegram / social / trading / wallet /
    enforcement term,
  * no real Discord / webhook / urlopen send call (AST call-name proof),
  * the harvest seam constructs NO old ungated dispatch / Stage 28.6 runner /
    private sink / transport adapter surface (AST call-name proof), so an old
    ungated dispatch is structurally impossible,
  * no filesystem write surface,
  * no transport-safety flag set ``True`` for a candidate,
  * no unbounded ``while`` loop / daemon,
  * no implicit I/O at import time (zero top-level Call nodes),
  * no Stage 30.11.7+ / Stage 31 file admitted by the Stage 30.11.6 inventory, and
  * the Stage 30.11.6 slice is a leaf: no OTHER stage30 file imports it.

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_6_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_6_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_6_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME,
    STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME,
    STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_BASENAME,
    STAGE30_11_6_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME,
    STAGE30_11_6_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE,
    STAGE30_11_6_TEST_BASENAMES,
    STAGE30_11_22_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_11_6_SCANNED_PRODUCTION_BASENAMES
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
# 1. Files exist + import cleanly + scanned set is the four modules
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_11_6_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.6 requires {basename}"
        )


def test_scanned_basenames_are_the_four_modules() -> None:
    assert STAGE30_11_6_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_6_ALLOWED_STAGE30_BASENAMES
    )
    assert len(STAGE30_11_6_SCANNED_PRODUCTION_BASENAMES) == 4


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_11_6_candidate_source_models  # noqa: F401
    import PHX2.stage30.stage30_11_6_stage29_projection_adapter  # noqa: F401,E501
    import PHX2.stage30.stage30_11_6_candidate_harvest_adapter  # noqa: F401
    import PHX2.stage30.stage30_11_6_fake_candidate_source_proof  # noqa: F401


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
                module in STAGE30_11_6_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_11_6_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.11.6 module {filename!r} imports non-allowlisted "
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
        assert forbidden not in STAGE30_11_6_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_11_6_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.11.6 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_models_import_no_phx2_module() -> None:
    # The Stage 30.11.6 models mirror the Stage 30.11.5 projection field names BY
    # VALUE, so (unlike the Stage 30.11.5 models) they import NO PHX2 module -- a
    # clean stdlib-only leaf.
    phx2 = _phx2_imports_of(STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME)
    assert phx2 == set(), (
        f"Stage 30.11.6 models must import no PHX2 module; found {sorted(phx2)}"
    )


def test_projection_adapter_imports_only_the_models_sibling() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME)
    assert phx2 == {"PHX2.stage30.stage30_11_6_candidate_source_models"}


def test_harvest_adapter_imports_only_the_own_siblings() -> None:
    # The harvest adapter composes ONLY the Stage 30.11.6 models + projection
    # adapter siblings -- it imports NO committed dispatch / runner / transport /
    # Stage 28 / 29 surface.
    phx2 = _phx2_imports_of(STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME)
    assert phx2 == {
        "PHX2.stage30.stage30_11_6_candidate_source_models",
        "PHX2.stage30.stage30_11_6_stage29_projection_adapter",
    }


def test_proof_composes_the_committed_stage_30_11_5_fake_proof() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_BASENAME)
    assert STAGE30_11_6_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE in phx2


def test_phx2_allowlist_stays_within_stage30_family() -> None:
    for module in STAGE30_11_6_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_6_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.11.6 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.11.6 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.11.6 module {filename!r} performs "
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
                    f"Stage 30.11.6 module {filename!r} imports database / "
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
                    f"Stage 30.11.6 module {filename!r} imports forbidden "
                    f"network / clock / concurrency module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / Stage 29.5 / PHX1 import (incl. Stage 27 / 28 / 29 record)
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
                    f"Stage 30.11.6 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            # A bare nested-record needle catches a NON-stage30 sneaky spelling of
            # a Stage 27 / 28 / 29 import. A stage30-family module name may itself
            # legitimately carry a ``stage2x`` token (the Stage 30.11.6
            # Stage-29-projection adapter is ``stage30_11_6_stage29_projection_
            # adapter``); the ``PHX2.stage21..29`` prefix check above already
            # forbids every REAL Stage 21-29 import, so the substring check skips
            # the stage30 family.
            if not module.startswith("PHX2.stage30."):
                for needle in ("stage27", "stage28", "stage29"):
                    assert needle not in module, (
                        f"Stage 30.11.6 module {filename!r} imports nested live "
                        f"candidate record / live provider module {module!r}"
                    )
            assert not module.startswith("PHX1"), (
                f"Stage 30.11.6 module {filename!r} imports PHX1 module "
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
            if module in STAGE30_11_6_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.11.6 module {filename!r} imports forbidden "
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
                f"Stage 30.11.6 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.11.6 module {filename!r} carries a transport scheme "
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
                f"Stage 30.11.6 module {filename!r} carries forbidden "
                f"surface term {term!r}"
            )


# ---------------------------------------------------------------------------
# 9. Composition discipline: no real send call; no dispatch / runner construction
# ---------------------------------------------------------------------------


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


def test_production_modules_call_no_real_send_surface() -> None:
    forbidden_call_substrings = (
        "discord",
        "web" + "hook",
        "urlopen",
    )
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for bad in forbidden_call_substrings:
                assert bad not in lowered, (
                    f"Stage 30.11.6 module {filename!r} calls a real send "
                    f"surface {name!r}"
                )


def test_harvest_seam_constructs_no_dispatch_or_runner_surface() -> None:
    # The harvest seam proper (models + projection adapter + harvest adapter) must
    # CALL none of the old ungated dispatch / Stage 28.6 runner / private sink /
    # transport-adapter / bounded-runner constructors -- so an old ungated dispatch
    # is structurally impossible in the harvest path. (The fake proof legitimately
    # composes the committed Stage 30.11.5 DIP-GATED fake proof, so it is exempt
    # here; the import allowlist already forbids it any Stage 28 / 29 surface.)
    forbidden_constructors = (
        "run_stage28_9_live_provider_session",
        "Stage28_6BoundedPrivateSessionRunner",
        "Stage28_9PrivateWebhookTransport",
        "make_stage30_11_private_dispatch_sink",
        "make_runtime_seam_compatible_sink",
        "make_stage30_11_5_private_transport_adapter",
        "run_stage30_11_5_bounded_live_runner",
        "run_stage30_11_runtime_gate_seam",
    )
    harvest_seam_basenames = (
        STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME,
        STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME,
        STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME,
    )
    for basename in harvest_seam_basenames:
        names = _called_names(_source_of(basename))
        for forbidden in forbidden_constructors:
            assert forbidden not in names, (
                f"Stage 30.11.6 harvest-seam module {basename!r} constructs / "
                f"calls a dispatch / runner surface {forbidden!r}"
            )


def test_no_filesystem_write_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in ("open(", "Path(", ".write_text(", ".write_bytes("):
            assert needle not in text, (
                f"Stage 30.11.6 module {filename!r} carries a filesystem "
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
                f"Stage 30.11.6 module {filename!r} sets {flag}=True"
            )


# ---------------------------------------------------------------------------
# 10. Runtime discipline: no unbounded loop / daemon
# ---------------------------------------------------------------------------


def test_no_while_loop_in_any_production_module() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.11.6 module {filename!r} carries a while loop "
                f"(no unbounded loop / daemon is allowed)"
            )


def test_no_daemon_or_thread_call_or_import_surface() -> None:
    needles = ("daemon", "thread", "spawn", "fork", "sleep")
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.11.6 module {filename!r} calls a daemon / "
                    f"thread surface {name!r}"
                )
        for module in _imports_of(text):
            lowered = module.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.11.6 module {filename!r} imports a daemon / "
                    f"thread surface {module!r}"
                )


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
            f"Stage 30.11.6 module {filename!r} carries an unexpected "
            f"top-level call (implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# 12. No Stage 30.11.7+ / Stage 31 file admitted by the Stage 30.11.6 inventory
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_11_7_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_11_6_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_6_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_11_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 6, (
                "Stage 30.11.6 inventory must not admit a Stage 30.11.7+ "
                f"file yet; offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.11.6 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )


# ---------------------------------------------------------------------------
# 13. The Stage 30.11.6 slice is a LEAF: no existing production file imports it
# ---------------------------------------------------------------------------


_STAGE_30_11_6_MODULE_PREFIX: str = "PHX2.stage30.stage30_11_6_"


def test_no_existing_stage30_file_imports_the_slice() -> None:
    own_basenames = set(STAGE30_11_6_ALLOWED_STAGE30_BASENAMES)
    # The SOLE permitted importer is the explicitly operator-authorized successor
    # slice Stage 30.11.22 (the real-fed dry-run wrapper), which DRIVES the committed
    # Stage 30.11.6 harvest seam (harvest_live_candidates) and READS the committed
    # Stage 30.11.6 candidate-projection type in its bridge (the permitted Stage
    # 30.11 scope expansion -- no prior slice imported the harvest seam). That
    # successor is NEW (not an edit of an existing file); every OTHER stage30 file is
    # still forbidden from importing the slice.
    admitted_successor_basenames = set(STAGE30_11_22_ALLOWED_STAGE30_BASENAMES)
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__" or not entry.name.endswith(".py"):
            continue
        if entry.name in own_basenames:
            continue
        if entry.name in admitted_successor_basenames:
            # The authorized Stage 30.11.22 successor PRODUCTION modules MAY drive the
            # committed Stage 30.11.6 harvest seam + read the projection type (the
            # permitted Stage 30.11 scope expansion); their own boundary test pins
            # exactly which Stage 30.11.6 modules they import.
            continue
        text = entry.read_text(encoding="utf-8")
        for module in _imports_of(text):
            assert not module.startswith(_STAGE_30_11_6_MODULE_PREFIX), (
                f"{entry.name!r} imports the Stage 30.11.6 slice "
                f"({module!r}); the slice is a leaf and is not wired into the "
                f"runtime (no existing production file may be edited to import "
                f"it)"
            )
