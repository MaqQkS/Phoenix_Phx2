"""Stage 30.11.3 private sink adapter boundary tests.

Scans the three Stage 30.11.3 production .py modules (the private sink models,
the private sink adapter, the fake private sink proof) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses`` / ``decimal`` -- NO ``time`` / ``datetime``),
  * a positive PHX2 import allowlist (the Stage 30.11.3 own models + adapter
    siblings plus the committed Stage 30.9.3 gate-models and Stage 30.11.2
    runtime-gate-models + seam + fake-proof the slice composes ONLY) -- which
    proves, by construction, that NO Stage 21-29 (incl. Stage 28 suppression /
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
  * the transport + compact body builder are INJECTED parameters, the sink
    calls the injected transport from a single call site, and the production
    modules define / import no real Discord / webhook / transport send,
  * no filesystem write surface,
  * no implicit I/O at import time (zero top-level Call nodes),
  * no unbounded ``while`` loop / daemon,
  * no Stage 30.11.4+ / Stage 31 file admitted by the Stage 30.11.3 inventory,
    and
  * the Stage 30.11.3 slice is a leaf: no OTHER stage30 file imports it, and the
    committed surfaces it composes do not import it back.

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_3_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME,
    STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME,
    STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
    STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME,
    STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
    STAGE30_11_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_11_3_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
    STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
    STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_3_TEST_BASENAMES,
    STAGE30_11_4_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_5_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_11_3_SCANNED_PRODUCTION_BASENAMES
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
    for basename in STAGE30_11_3_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.3 requires {basename}"
        )


def test_scanned_basenames_are_the_three_modules() -> None:
    assert STAGE30_11_3_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME,
        STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME,
        STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME,
    )


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_11_3_private_sink_models  # noqa: F401
    import PHX2.stage30.stage30_11_3_private_sink_adapter  # noqa: F401
    import PHX2.stage30.stage30_11_3_fake_private_sink_proof  # noqa: F401,E501


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
                module in STAGE30_11_3_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_11_3_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.11.3 module {filename!r} imports non-allowlisted "
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
        assert forbidden not in STAGE30_11_3_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_11_3_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.11.3 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_models_import_no_phx2_module() -> None:
    # The private sink models are pure scalars / closed-set tokens; they embed
    # no committed record type and so import no PHX2 module (mirrors Stage
    # 30.9.3 / 30.11.2 models).
    phx2 = _phx2_imports_of(STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME)
    assert phx2 == set(), (
        "Stage 30.11.3 private sink models must import no PHX2 module; found "
        f"{sorted(phx2)}"
    )


def test_adapter_phx2_imports_are_the_committed_composition() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME)
    assert phx2 == {
        STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
        STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE,
        STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
    }, (
        "Stage 30.11.3 adapter must import its own models plus the committed "
        "Stage 30.9.3 gate-models + Stage 30.11.2 runtime-gate-models siblings; "
        f"found {sorted(phx2)}"
    )


def test_proof_phx2_imports_are_models_adapter_and_committed() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME)
    assert phx2 == {
        STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
        STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
        STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE,
        STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
        STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
        STAGE30_11_3_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
    }, (
        "Stage 30.11.3 fake proof must import its own models + adapter plus the "
        "committed gate-input + Stage 30.11.2 seam / models / fake-proof "
        f"siblings; found {sorted(phx2)}"
    )


def test_phx2_allowlist_stays_within_stage30_family() -> None:
    for module in STAGE30_11_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_3_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.11.3 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.11.3 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.11.3 module {filename!r} performs "
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
                    f"Stage 30.11.3 module {filename!r} imports database / "
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
                    f"Stage 30.11.3 module {filename!r} imports forbidden "
                    f"network / clock / concurrency module {module!r}"
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
                    f"Stage 30.11.3 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            assert "stage28" not in module, (
                f"Stage 30.11.3 module {filename!r} imports Stage 28 module "
                f"{module!r}"
            )
            assert "stage29" not in module, (
                f"Stage 30.11.3 module {filename!r} imports Stage 29 module "
                f"{module!r}"
            )
            assert not module.startswith("PHX1"), (
                f"Stage 30.11.3 module {filename!r} imports PHX1 module "
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
            if module in STAGE30_11_3_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.11.3 module {filename!r} imports forbidden "
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
                f"Stage 30.11.3 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.11.3 module {filename!r} carries a transport scheme "
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
                f"Stage 30.11.3 module {filename!r} carries forbidden "
                f"surface term {term!r}"
            )


# ---------------------------------------------------------------------------
# 9. Transport + builder are INJECTED; one transport call site; no real send
# ---------------------------------------------------------------------------


def _adapter_function_def(name: str) -> ast.FunctionDef:
    tree = _module_ast(_source_of(STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"adapter function {name!r} absent")


def test_sink_factory_injects_transport_builder_and_clock() -> None:
    fn = _adapter_function_def("make_stage30_11_private_dispatch_sink")
    kwonly = {a.arg for a in fn.args.kwonlyargs}
    for required in ("transport", "compact_body_builder", "created_at_utc"):
        assert required in kwonly, (
            f"Stage 30.11.3 sink factory must inject {required!r} as a "
            f"keyword-only parameter"
        )


def test_injected_transport_has_exactly_one_call_site_in_the_sink() -> None:
    # The injected ``transport`` is called from exactly one site (after a valid
    # request is built). AST proof over Call nodes whose callee is the Name
    # ``transport``.
    fn = _adapter_function_def("make_stage30_11_private_dispatch_sink")
    call_sites = 0
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "transport":
                call_sites += 1
    assert call_sites == 1, (
        "Stage 30.11.3 sink must call the injected transport from exactly one "
        f"site; found {call_sites}"
    )


def test_production_modules_call_no_real_send_surface() -> None:
    # No production module CALLS a Discord / webhook / urlopen send-like
    # function (AST call-name proof; the injected ``transport`` callable and the
    # request / result constructors are legitimately named and not scanned --
    # the import allowlist already forbids any real transport module).
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
                    f"Stage 30.11.3 module {filename!r} calls a real send "
                    f"surface {name!r}"
                )


def test_no_filesystem_write_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in ("open(", "Path(", ".write_text(", ".write_bytes("):
            assert needle not in text, (
                f"Stage 30.11.3 module {filename!r} carries a filesystem "
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
                f"Stage 30.11.3 module {filename!r} sets {flag}=True"
            )


# ---------------------------------------------------------------------------
# 10. Runtime discipline: no unbounded loop / daemon
# ---------------------------------------------------------------------------


def test_no_while_loop_in_any_production_module() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.11.3 module {filename!r} carries a while loop "
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
                    f"Stage 30.11.3 module {filename!r} calls a daemon / "
                    f"thread surface {name!r}"
                )
        for module in _imports_of(text):
            lowered = module.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.11.3 module {filename!r} imports a daemon / "
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
            f"Stage 30.11.3 module {filename!r} carries an unexpected "
            f"top-level call (implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# 12. No Stage 30.11.4+ / Stage 31 file admitted by the Stage 30.11.3 inventory
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_11_4_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_11_3_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_3_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_11_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 3, (
                "Stage 30.11.3 inventory must not admit a Stage 30.11.4+ "
                f"file yet; offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.11.3 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )


# ---------------------------------------------------------------------------
# 13. The Stage 30.11.3 slice is a LEAF: no existing production file imports it
# ---------------------------------------------------------------------------


_STAGE_30_11_3_MODULE_PREFIX: str = "PHX2.stage30.stage30_11_3_"


def test_no_existing_stage30_file_imports_the_slice() -> None:
    # The Stage 30.11.3 private sink adapter's ONLY permitted consumers are the
    # now-admitted Stage 30.11.4 offline end-to-end proof slice (whose proof
    # composes the committed adapter + fake transport behind the dip gate) and the
    # now-admitted Stage 30.11.5 controlled live ceremony wiring slice (whose
    # transport adapter composes the committed sink request / result types and
    # whose bounded runner composes the committed private sink) -- the permitted
    # Stage 30.11 scope expansion. Every OTHER stage30 file (Stage 28 / 29 /
    # existing Stage 30 production, incl. the committed Stage 30.11.2 seam) must
    # still not import the Stage 30.11.3 slice: the adapter is not wired into any
    # pre-existing runtime / orchestrator / transport path.
    allowed_importers = (
        set(STAGE30_11_3_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_4_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_5_ALLOWED_STAGE30_BASENAMES)
    )
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__" or not entry.name.endswith(".py"):
            continue
        if entry.name in allowed_importers:
            continue
        text = entry.read_text(encoding="utf-8")
        for module in _imports_of(text):
            assert not module.startswith(_STAGE_30_11_3_MODULE_PREFIX), (
                f"{entry.name!r} imports the Stage 30.11.3 slice "
                f"({module!r}); only the Stage 30.11.4 offline end-to-end proof "
                f"slice may compose the adapter -- no other (Stage 28 / 29 / "
                f"existing Stage 30) production file may be edited to import it"
            )


def test_composed_committed_surfaces_do_not_import_the_slice() -> None:
    # The slice DEPENDS ON the committed Stage 30.9.3 gate models + Stage 30.11.2
    # seam / models / fake proof; the dependency must point one direction only
    # (those committed files must not import the Stage 30.11.3 slice).
    for basename in (
        "stage30_9_3_dip_filtered_live_gate_models.py",
        "stage30_11_2_runtime_gate_models.py",
        "stage30_11_2_runtime_gate_seam.py",
        "stage30_11_2_fake_runtime_gate_proof.py",
    ):
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"expected {path} to exist"
        for module in _imports_of(path.read_text(encoding="utf-8")):
            assert not module.startswith(_STAGE_30_11_3_MODULE_PREFIX), (
                f"committed file {basename!r} must not import the Stage "
                f"30.11.3 slice ({module!r})"
            )


def test_scanned_and_test_basenames_carry_no_secret_terms() -> None:
    names: List[str] = list(STAGE30_11_3_ALLOWED_STAGE30_BASENAMES) + list(
        STAGE30_11_3_TEST_BASENAMES
    )
    for name in names:
        lower = name.lower()
        for forbidden in ("secret", "web" + "hook", "token_url", "api_key"):
            assert forbidden not in lower, (
                f"Stage 30.11.3 basename {name!r} carries forbidden term "
                f"{forbidden!r}"
            )
