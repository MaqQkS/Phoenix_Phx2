"""Stage 30.11.19 market-context enrichment boundary tests.

Scans the three Stage 30.11.19 production .py modules (the enrichment models, the
enrichment adapter, the fake enrichment proof) for:

  * a positive stdlib import allowlist (``__future__`` / ``typing`` /
    ``dataclasses`` ONLY -- the Layer-0 positivity + ISO-shape checks REUSE the
    committed Stage 30.11.18 predicates, so no decimal / datetime / os / network);
  * a positive PHX2 import allowlist (the own siblings plus the committed Stage
    30.11.18 facts models + adapter, the committed Stage 30.11.17 models, and the
    committed Stage 30.11.15 in-memory ledger + Stage 30.11.5 recording fake
    client) -- proving NO Stage 21-29 import, NO Stage 30.4.3 Birdeye source
    import, NO Stage 30.11.16 real-send guard import, and NO real harvest adapter
    import;
  * no ``os.environ`` / ``os.getenv`` access;
  * no database / SQLite / compression surface import;
  * no network / concurrency / clock import;
  * no Stage 21-29 / PHX1 import;
  * no forbidden secret / transport / URL text needle (the family set MINUS the
    ``endpoint_secret`` keyword the adapter / proof forward to the committed
    Stage 30.11.18 session) and no ``://`` literal;
  * no filesystem-write surface (persistence belongs to the injected ledger only);
  * no implicit I/O at import time (zero top-level Call nodes);
  * no unbounded ``while`` loop / daemon / thread surface;
  * the Stage 30.11.19 inventory admits no Stage 30.11.20+ / Stage 31 file.

Fake / offline / no-send only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_19_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_19_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_19_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_19_ENRICHMENT_ADAPTER_BASENAME,
    STAGE30_11_19_ENRICHMENT_MODELS_BASENAME,
    STAGE30_11_19_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_19_TEST_BASENAMES,
    STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# The Stage 30.11.19 text-needle set: the family set MINUS the ``endpoint_secret``
# KEYWORD the adapter + fake proof forward to the committed Stage 30.11.18 session
# (a safe param name, not a secret value). Mirrors the committed Stage 30.11.18 /
# 30.11.17 needle-set deviation.
_ENDPOINT_SECRET_NEEDLE: str = "endpoint" + "_secret"
_NEEDLES: Tuple[str, ...] = tuple(
    n for n in STAGE30_11_FORBIDDEN_TEXT_NEEDLES if n != _ENDPOINT_SECRET_NEEDLE
)


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_11_19_SCANNED_PRODUCTION_BASENAMES
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
# 1. Files exist + scanned set is the three modules + import cleanly
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_11_19_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.19 requires {basename}"
        )


def test_scanned_basenames_are_the_three_modules() -> None:
    assert STAGE30_11_19_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_19_ALLOWED_STAGE30_BASENAMES
    )
    assert len(STAGE30_11_19_SCANNED_PRODUCTION_BASENAMES) == 3


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_11_19_market_context_enrichment_models  # noqa: F401,E501
    import PHX2.stage30.stage30_11_19_market_context_enrichment_adapter  # noqa: F401,E501
    import PHX2.stage30.stage30_11_19_fake_market_context_enrichment_proof  # noqa: F401,E501


# ---------------------------------------------------------------------------
# 2. Positive stdlib + PHX2 import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_in_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            top = module.split(".")[0]
            assert (
                module in STAGE30_11_19_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_11_19_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.11.19 module {filename!r} imports non-allowlisted "
                f"stdlib module {module!r}"
            )


def test_stdlib_allowlist_excludes_io_db_and_clock() -> None:
    # The Layer-0 checks REUSE the committed Stage 30.11.18 predicates, so no
    # decimal / datetime / os / db / clock is admitted here.
    for forbidden in (
        "os",
        "json",
        "pathlib",
        "datetime",
        "decimal",
        "sqlite3",
        "time",
    ):
        assert forbidden not in STAGE30_11_19_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_11_19_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.11.19 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_phx2_allowlist_stays_within_stage30_family() -> None:
    for module in STAGE30_11_19_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_19_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "renderer", "live_provider", "stage28"):
        assert forbidden not in joined


def test_models_module_imports_no_phx2() -> None:
    # The models module is a pure leaf (mirrors the Stage 30.11.18 / 30.11.17
    # models).
    assert _phx2_imports_of(
        STAGE30_11_19_ENRICHMENT_MODELS_BASENAME
    ) == set()


def test_adapter_runs_the_committed_30_11_18_session() -> None:
    phx2 = _phx2_imports_of(STAGE30_11_19_ENRICHMENT_ADAPTER_BASENAME)
    assert (
        "PHX2.stage30.stage30_11_18_harvest_to_curated_adapter" in phx2
    ), (
        "the Stage 30.11.19 adapter must run the committed Stage 30.11.18 "
        "curated session"
    )
    assert (
        "PHX2.stage30.stage30_11_18_harvested_facts_models" in phx2
    ), (
        "the Stage 30.11.19 adapter must build the committed Stage 30.11.18 "
        "facts type"
    )


# ---------------------------------------------------------------------------
# 3. No Birdeye / Stage 30.4.3 source, no Stage 30.11.16 guard, no real harvest
# ---------------------------------------------------------------------------


def test_no_birdeye_source_or_stage_30_4_3_import() -> None:
    # The market-context source is INJECTED duck-typed; committed Stage 30.11.19
    # constructs no real provider transport and imports neither the Stage 30.4.3
    # Birdeye source nor any Birdeye / provider module.
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            assert "stage30_4_3" not in module, (
                f"Stage 30.11.19 module {filename!r} imports the Stage 30.4.3 "
                f"source {module!r}; the market-context source is injected "
                f"duck-typed"
            )
            assert "birdeye" not in module.lower(), (
                f"Stage 30.11.19 module {filename!r} imports a provider module "
                f"{module!r}"
            )


def test_no_stage_30_11_16_real_send_guard_import() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            assert "stage30_11_16" not in module, (
                f"Stage 30.11.19 module {filename!r} imports the Stage 30.11.16 "
                f"real-send guard {module!r}; this stage is no-send"
            )


def test_no_real_harvest_adapter_import() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            assert "candidate_harvest" not in module, (
                f"Stage 30.11.19 module {filename!r} imports a real harvest "
                f"adapter {module!r}"
            )
            assert "stage30_11_6_" not in module, (
                f"Stage 30.11.19 module {filename!r} imports Stage 30.11.6 "
                f"{module!r}"
            )


# ---------------------------------------------------------------------------
# 4. No env / db / network / stage21-29 / PHX1 imports
# ---------------------------------------------------------------------------


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.11.19 module {filename!r} performs "
                    f"os.{node.attr} access"
                )


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
                    f"Stage 30.11.19 module {filename!r} imports database / "
                    f"compression surface {module!r}"
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
    "sched",
    "random",
    "datetime",
)


def test_no_network_concurrency_or_clock_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_OR_CONCURRENCY_MODULES:
                assert not (
                    module == forbidden or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.11.19 module {filename!r} imports forbidden "
                    f"network / concurrency / clock module {module!r}"
                )


def test_no_stage21_29_or_phx1_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for stage_n in range(21, 30):
                prefix = f"PHX2.stage{stage_n}"
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.11.19 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.11.19 module {filename!r} imports PHX1 {module!r}"
            )


# ---------------------------------------------------------------------------
# 5. No forbidden secret / transport / URL needles + no scheme literal
# ---------------------------------------------------------------------------


def test_needle_set_deviation_is_only_endpoint_secret() -> None:
    family = set(STAGE30_11_FORBIDDEN_TEXT_NEEDLES)
    own = set(_NEEDLES)
    assert family - own == {_ENDPOINT_SECRET_NEEDLE}
    for needle in (
        "discord" + ".com",
        "/web" + "hooks/",
        "b" + "earer",
        "api_" + "key",
        "h" + "ttps://",
        "chain" + "stack",
        "public-api.birdeye" + ".so",
    ):
        assert needle in own


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in _NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.11.19 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.11.19 module {filename!r} carries a transport scheme "
            f"literal"
        )


# ---------------------------------------------------------------------------
# 6. No filesystem-write surface (persistence belongs to the injected ledger)
# ---------------------------------------------------------------------------


_FS_WRITE_NEEDLES: Tuple[str, ...] = (
    "open(",
    "Path(",
    ".write_text(",
    ".write_bytes(",
    ".mkdir(",
)


def test_no_filesystem_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in _FS_WRITE_NEEDLES:
            assert needle not in text, (
                f"Stage 30.11.19 module {filename!r} carries a filesystem "
                f"surface {needle!r} (persistence belongs to the injected "
                f"ledger only)"
            )


# ---------------------------------------------------------------------------
# 7. No implicit I/O at import time + no unbounded loop / daemon / thread
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
            f"Stage 30.11.19 module {filename!r} carries a top-level call "
            f"(implicit I/O at import time)"
        )


def test_no_while_loop_in_any_production_module() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            assert not isinstance(node, ast.While), (
                f"Stage 30.11.19 module {filename!r} carries a while loop"
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


def test_no_daemon_or_thread_surface() -> None:
    needles = ("daemon", "thread", "spawn", "fork", "sleep")
    for filename, text in _scanned_sources().items():
        for name in _called_names(text):
            lowered = name.lower()
            for needle in needles:
                assert needle not in lowered, (
                    f"Stage 30.11.19 module {filename!r} calls a daemon / "
                    f"thread surface {name!r}"
                )


# ---------------------------------------------------------------------------
# 8. No Stage 30.11.20+ / Stage 31 file admitted by the Stage 30.11.19 inventory
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_11_20_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_11_19_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_19_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_11_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 19, (
                "Stage 30.11.19 inventory must not admit a Stage 30.11.20+ "
                f"file; offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.11.19 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )
