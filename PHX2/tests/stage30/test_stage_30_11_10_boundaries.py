"""Stage 30.11.10 real ATH-resolver boundary tests.

Scans the three Stage 30.11.10 production .py modules (the ATH-resolver models, the
ATH-resolver adapter, the fake ATH-resolver proof) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses`` -- NO ``decimal`` (the slice carries the committed drawdown VERBATIM,
    never coercing it), NO ``re``, NO ``time`` / ``datetime``),
  * a positive PHX2 import allowlist (the Stage 30.11.10 OWN three siblings ONLY) --
    which proves, by construction, that the Stage 30.11.10 production slice is a clean
    LEAF: it imports NO Stage 30.7 display bridge / Stage 30.11.5 / 30.11.6 / 30.11.7 /
    30.11.8 / 30.11.9 module (so those committed leaf boundary tests stay green; importing
    the Stage 30.11.7 slice would break its "no existing stage30 file imports the slice"
    test) and NO Stage 21-29 / runtime orchestrator / renderer / real transport / live
    provider / network module,
  * no ``os`` import / ``os.environ`` access; no db / compression / network / clock /
    concurrency import; no Stage 21-29 / PHX1 import; no forbidden secret / transport /
    URL needle; no public / social / trading / wallet / enforcement term; no real send
    call; no runner / transport / dispatch / confirmation / enrichment construction; no
    filesystem write; no transport-safety flag set True; no unbounded loop / daemon; no
    implicit I/O at import time; NO BROAD PREFIX allowlist; no Stage 30.11.11+ / Stage 31
    file in the inventory; and the slice is a leaf (no OTHER stage30 file imports it).

Fake / offline only. No live call, no provider, no private send, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_10_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_10_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_10_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_13_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_10_ATH_RESOLVER_ADAPTER_BASENAME,
    STAGE30_11_10_ATH_RESOLVER_ADAPTER_MODULE,
    STAGE30_11_10_ATH_RESOLVER_MODELS_BASENAME,
    STAGE30_11_10_ATH_RESOLVER_MODELS_MODULE,
    STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_BASENAME,
    STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_MODULE,
    STAGE30_11_10_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_10_TEST_BASENAMES,
    STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_11_10_SCANNED_PRODUCTION_BASENAMES
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


# ---------------------------------------------------------------------------
# 1. Files exist + import cleanly + scanned set is the three modules
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_11_10_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.10 requires {basename}"
        )


def test_scanned_basenames_are_the_three_modules() -> None:
    assert STAGE30_11_10_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_10_ALLOWED_STAGE30_BASENAMES
    )
    assert len(STAGE30_11_10_SCANNED_PRODUCTION_BASENAMES) == 3


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_11_10_ath_resolver_models  # noqa: F401
    import PHX2.stage30.stage30_11_10_ath_resolver_adapter  # noqa: F401
    import PHX2.stage30.stage30_11_10_fake_ath_resolver_proof  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Positive stdlib + PHX2 import allowlists (the slice is a LEAF)
# ---------------------------------------------------------------------------


def test_non_phx2_imports_are_in_stdlib_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            top = module.split(".")[0]
            assert (
                module in STAGE30_11_10_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_11_10_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.11.10 module {filename!r} imports non-allowlisted "
                f"stdlib / third-party module {module!r}"
            )


def test_stdlib_allowlist_excludes_decimal_re_io_db_and_clock_surfaces() -> None:
    for forbidden in (
        "decimal",
        "re",
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
        assert forbidden not in STAGE30_11_10_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_11_10_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.11.10 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_exactly_the_three_own_siblings() -> None:
    assert STAGE30_11_10_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_10_ATH_RESOLVER_MODELS_MODULE,
        STAGE30_11_10_ATH_RESOLVER_ADAPTER_MODULE,
        STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_MODULE,
    )
    assert len(STAGE30_11_10_ALLOWED_PHX2_IMPORTS) == 3


def test_no_broad_prefix_allowlist() -> None:
    for module in STAGE30_11_10_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_11_10_")
        assert len(module.split(".")) >= 3
        assert len(module.split(".")[-1]) > len("stage30_11_10_")
        assert not module.endswith(".")
        assert "*" not in module
    for prefix in ("PHX2", "PHX2.stage30", "PHX2.stage30.stage30_11_10_"):
        assert prefix not in STAGE30_11_10_ALLOWED_PHX2_IMPORTS


def test_models_import_no_phx2_module() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_10_ATH_RESOLVER_MODELS_BASENAME)
    assert phx2 == set(), (
        f"Stage 30.11.10 models must import no PHX2 module; found {sorted(phx2)}"
    )


def test_adapter_imports_only_the_models_sibling() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_10_ATH_RESOLVER_ADAPTER_BASENAME)
    assert phx2 == {STAGE30_11_10_ATH_RESOLVER_MODELS_MODULE}


def test_proof_imports_only_the_own_siblings() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_10_FAKE_ATH_RESOLVER_PROOF_BASENAME)
    assert phx2 == {
        STAGE30_11_10_ATH_RESOLVER_MODELS_MODULE,
        STAGE30_11_10_ATH_RESOLVER_ADAPTER_MODULE,
    }


def test_production_slice_imports_no_blocked_stage30_module() -> None:
    # The KEY leaf invariant: no Stage 30.11.10 PRODUCTION module imports the Stage 30.7
    # display bridge or a Stage 30.11.5 / 30.11.6 / 30.11.7 / 30.11.8 / 30.11.9 module, so
    # those committed leaf boundary tests stay green (importing the Stage 30.11.7 slice
    # would break its committed "no existing stage30 file imports the slice" test, and the
    # Stage 30.7 display bridge is deliberately NOT the runtime resolver). The committed
    # adapters + Stage 27.4 reader are composed only by the Stage 30.11.10 TEST.
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden_prefix in (
                "PHX2.stage30.stage30_7_",
                "PHX2.stage30.stage30_11_5_",
                "PHX2.stage30.stage30_11_6_",
                "PHX2.stage30.stage30_11_7_",
                "PHX2.stage30.stage30_11_8_",
                "PHX2.stage30.stage30_11_9_",
            ):
                assert not module.startswith(forbidden_prefix), (
                    f"{filename!r} imports a leaf-breaking module {module!r}"
                )


def test_phx2_allowlist_stays_within_stage30_family() -> None:
    for module in STAGE30_11_10_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_11_10_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_10_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.11.10 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.11.10 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.11.10 module {filename!r} performs "
                    f"os.{node.attr} access"
                )


# ---------------------------------------------------------------------------
# 4. No database / compression / network / concurrency / clock / decimal imports
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
                    f"Stage 30.11.10 module {filename!r} imports database / "
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
    "re",
    "decimal",
)


def test_no_network_clock_concurrency_re_or_decimal_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_CLOCK_OR_CONCURRENCY_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.11.10 module {filename!r} imports forbidden "
                    f"network / clock / concurrency / re / decimal module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / PHX1 import
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
                    f"Stage 30.11.10 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            if not module.startswith("PHX2.stage30."):
                for needle in ("stage27", "stage28", "stage29"):
                    assert needle not in module, (
                        f"Stage 30.11.10 module {filename!r} imports nested live "
                        f"candidate record / live provider module {module!r}"
                    )
            assert not module.startswith("PHX1"), (
                f"Stage 30.11.10 module {filename!r} imports PHX1 module "
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
            if module in STAGE30_11_10_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.11.10 module {filename!r} imports forbidden "
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
                f"Stage 30.11.10 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.11.10 module {filename!r} carries a transport scheme "
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
                f"Stage 30.11.10 module {filename!r} carries forbidden "
                f"surface term {term!r}"
            )


# ---------------------------------------------------------------------------
# 9. Composition discipline: no real send call; no runner / transport construction
# ---------------------------------------------------------------------------


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
                    f"Stage 30.11.10 module {filename!r} calls a real send "
                    f"surface {name!r}"
                )


def test_source_constructs_no_runner_transport_or_other_slice_surface() -> None:
    forbidden_constructors = (
        "run_stage28_9_live_provider_session",
        "Stage28_6BoundedPrivateSessionRunner",
        "Stage28_9PrivateWebhookTransport",
        "make_stage30_11_private_dispatch_sink",
        "make_runtime_seam_compatible_sink",
        "make_stage30_11_5_private_transport_adapter",
        "run_stage30_11_5_bounded_live_runner",
        "run_stage30_11_runtime_gate_seam",
        "run_stage30_11_5_fake_live_wiring_proof",
        "harvest_live_candidates",
        "enrich_harvested_candidate",
        "enrich_candidate_source",
        "build_migration_resolver",
        "resolve_candidate_migration",
        "build_migration_evidence_source",
        "read_price_context",
        "read_migration_context",
        "build_sanitized_ath_bridge",
    )
    for filename, text in _scanned_sources().items():
        names = _called_names(text)
        for forbidden in forbidden_constructors:
            assert forbidden not in names, (
                f"Stage 30.11.10 module {filename!r} constructs / calls a "
                f"runner / transport / other-slice surface {forbidden!r}"
            )


def test_no_filesystem_write_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in ("open(", "Path(", ".write_text(", ".write_bytes("):
            assert needle not in text, (
                f"Stage 30.11.10 module {filename!r} carries a filesystem "
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
                f"Stage 30.11.10 module {filename!r} sets {flag}=True"
            )


# ---------------------------------------------------------------------------
# 10. Runtime discipline: no unbounded loop / daemon
# ---------------------------------------------------------------------------


def test_no_while_loop_in_any_production_module() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.11.10 module {filename!r} carries a while loop "
                f"(no unbounded loop / daemon is allowed)"
            )


def test_no_daemon_or_thread_call_or_import_surface() -> None:
    needles = ("daemon", "thread", "spawn", "fork", "sleep")
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.11.10 module {filename!r} calls a daemon / "
                    f"thread surface {name!r}"
                )
        for module in _imports_of(text):
            lowered = module.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.11.10 module {filename!r} imports a daemon / "
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
            f"Stage 30.11.10 module {filename!r} carries an unexpected "
            f"top-level call (implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# 12. No Stage 30.11.11+ / Stage 31 file admitted by the Stage 30.11.10 inventory
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_11_11_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_11_10_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_10_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_11_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 10, (
                "Stage 30.11.10 inventory must not admit a Stage 30.11.11+ "
                f"file yet; offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.11.10 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )


# ---------------------------------------------------------------------------
# 13. The Stage 30.11.10 slice is a LEAF: no existing production file imports it
# ---------------------------------------------------------------------------


_STAGE_30_11_10_MODULE_PREFIX: str = "PHX2.stage30.stage30_11_10_"


def test_no_existing_stage30_file_imports_the_slice() -> None:
    # The Stage 30.11.13 committed no-send composer + its fake proof (the
    # integration capstone) are the SOLE permitted importers of this leaf.
    own_basenames = set(STAGE30_11_10_ALLOWED_STAGE30_BASENAMES) | set(
        STAGE30_11_13_ALLOWED_STAGE30_BASENAMES
    )
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__" or not entry.name.endswith(".py"):
            continue
        if entry.name in own_basenames:
            continue
        text = entry.read_text(encoding="utf-8")
        for module in _imports_of(text):
            assert not module.startswith(_STAGE_30_11_10_MODULE_PREFIX), (
                f"{entry.name!r} imports the Stage 30.11.10 slice "
                f"({module!r}); the slice is a leaf and is not wired into the "
                f"runtime (no existing production file may be edited to import "
                f"it)"
            )
