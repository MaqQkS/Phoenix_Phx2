"""Stage 30.10.1 production-file boundary tests.

Scans the two Stage 30.10.1 production .py modules (the eligibility models +
the classifier) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses`` / ``decimal`` / ``re``),
  * a positive PHX2 import allowlist (the models module imports NO PHX2
    module; the classifier imports ONLY the Stage 30.10.1 models sibling) --
    which proves, by construction, that NO Stage 21-29 (incl. Stage 28
    suppression / Stage 29.5) / Stage 30.3 / Stage 30.4 runtime orchestrator
    / renderer / Discord / provider / network module is imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` access,
  * no database / SQLite / compression surface import,
  * no network / secret / subprocess / threading / async / time import,
  * no Stage 21-29 / Stage 29.5 / PHX1 import,
  * no Discord / provider / runtime / orchestrator / renderer import surface,
  * no forbidden secret / transport / URL text needle and no ``://`` literal,
  * no public / subscriber / paid / Telegram / social / trading / wallet /
    enforcement term (those live only in the manifest constants / the tests),
  * no implicit I/O at import time (the only top-level Call nodes are the
    pure ``re.compile`` and the all-default policy construction),
  * no Stage 30.10.2+ file admitted by the manifest inventory, and
  * no existing runtime orchestrator / renderer / transport / Stage 28
    suppression / manifest file imports the Stage 30.10.1 slice (the slice
    is a leaf; nothing existing depends on it).

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_10_manifest import (
    STAGE30_10_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_10_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_10_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME,
    STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME,
    STAGE30_10_1_ELIGIBILITY_MODELS_MODULE,
    STAGE30_10_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_10_1_TEST_BASENAMES,
    STAGE30_10_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_10_1_SCANNED_PRODUCTION_BASENAMES
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
# 1. Files exist + import cleanly + scanned set is the two modules
# ---------------------------------------------------------------------------


def test_production_files_exist() -> None:
    for basename in STAGE30_10_1_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.10.1 requires {basename}"
        )


def test_scanned_basenames_are_the_two_modules() -> None:
    assert STAGE30_10_1_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME,
        STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME,
    )


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_10_1_tier_dip_eligibility_models  # noqa: F401
    import PHX2.stage30.stage30_10_1_tier_dip_eligibility_classifier  # noqa: F401,E501


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
                module in STAGE30_10_1_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_10_1_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.10.1 module {filename!r} imports non-allowlisted "
                f"stdlib / third-party module {module!r}"
            )


def test_models_import_no_phx2_module() -> None:
    phx2 = _phx2_imports_of(STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME)
    assert phx2 == set(), (
        "Stage 30.10.1 eligibility models must import no PHX2 module; found "
        f"{sorted(phx2)}"
    )


def test_classifier_phx2_imports_are_exactly_the_models_sibling() -> None:
    phx2 = _phx2_imports_of(STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME)
    assert phx2 == {STAGE30_10_1_ELIGIBILITY_MODELS_MODULE}, (
        "Stage 30.10.1 classifier must import only the Stage 30.10.1 models "
        f"sibling; found {sorted(phx2)}"
    )


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_10_1_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.10.1 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_the_models_sibling_only() -> None:
    assert STAGE30_10_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_10_1_ELIGIBILITY_MODELS_MODULE,
    )
    for module in STAGE30_10_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.10.1 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.10.1 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.10.1 module {filename!r} performs "
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
                    f"Stage 30.10.1 module {filename!r} imports database / "
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
                    f"Stage 30.10.1 module {filename!r} imports forbidden "
                    f"network / secret / concurrency module {module!r}"
                )


def test_no_sleep_call_surface() -> None:
    for filename, text in _scanned_sources().items():
        assert "sleep(" not in text, (
            f"Stage 30.10.1 module {filename!r} carries a sleep call surface"
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
                    f"Stage 30.10.1 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            assert "stage28" not in module, (
                f"Stage 30.10.1 module {filename!r} imports Stage 28 module "
                f"{module!r}"
            )
            assert "stage29" not in module, (
                f"Stage 30.10.1 module {filename!r} imports Stage 29 / 29.5 "
                f"module {module!r}"
            )
            assert not module.startswith("PHX1"), (
                f"Stage 30.10.1 module {filename!r} imports PHX1 module "
                f"{module!r}"
            )


# ---------------------------------------------------------------------------
# 6. No Discord / provider / runtime / orchestrator / renderer import surface
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
    "live_provider",
    "suppress",
)


def test_no_provider_runtime_or_renderer_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module in STAGE30_10_1_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.10.1 module {filename!r} imports forbidden "
                    f"surface {needle!r}; offender {module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden secret / transport / URL text needles
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_10_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.10.1 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.10.1 module {filename!r} carries a transport scheme "
            f"literal"
        )


# ---------------------------------------------------------------------------
# 8. No public / subscriber / paid / social / trading / wallet / enforcement
#    term in production modules
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
                f"Stage 30.10.1 module {filename!r} carries forbidden "
                f"surface term {term!r}"
            )


# ---------------------------------------------------------------------------
# 9. No implicit I/O at import time (constrained top-level Call nodes)
# ---------------------------------------------------------------------------
#
# The only top-level Call nodes the Stage 30.10.1 production modules may carry
# are the pure ``re.compile`` of the ISO-8601 pattern (an Attribute call) and
# the all-default fail-closed policy construction (a Name call of the policy
# dataclass). Neither performs any I/O at import time. Decorator-list Calls
# (``@dataclass(frozen=True)``) are not body statements and are not scanned.


_ALLOWED_TOP_LEVEL_CALL_NAMES: Tuple[str, ...] = (
    "Stage30_10DipEligibilityPolicy",
)
_ALLOWED_TOP_LEVEL_CALL_ATTRS: Tuple[str, ...] = (
    "compile",
)


def _top_level_call_values(tree: ast.Module):
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            yield stmt.value
        elif isinstance(stmt, ast.Assign) and isinstance(
            stmt.value, ast.Call
        ):
            yield stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(
            stmt.value, ast.Call
        ):
            yield stmt.value


def test_no_unexpected_top_level_call_nodes() -> None:
    for filename, text in _scanned_sources().items():
        for call in _top_level_call_values(_module_ast(text)):
            func = call.func
            if isinstance(func, ast.Name):
                assert func.id in _ALLOWED_TOP_LEVEL_CALL_NAMES, (
                    f"Stage 30.10.1 module {filename!r} carries an "
                    f"unexpected top-level call {func.id!r}"
                )
            elif isinstance(func, ast.Attribute):
                assert func.attr in _ALLOWED_TOP_LEVEL_CALL_ATTRS, (
                    f"Stage 30.10.1 module {filename!r} carries an "
                    f"unexpected top-level attribute call .{func.attr}"
                )
            else:  # pragma: no cover - defensive
                raise AssertionError(
                    f"Stage 30.10.1 module {filename!r} carries an "
                    f"unexpected top-level call shape"
                )


# ---------------------------------------------------------------------------
# 10. No Stage 30.10.2+ file admitted by the manifest inventory
# ---------------------------------------------------------------------------


_STAGE_30_10_MINOR_RE = re.compile(r"stage_?30_10_(\d+)")


def test_manifest_inventory_admits_no_stage_30_10_2_plus_file() -> None:
    inventory = (
        tuple(STAGE30_10_1_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_10_1_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_10_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 2:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.10.1 manifest inventory must not admit a Stage 30.10.2+ "
        f"file yet; saw {violations!r}"
    )


def test_inventory_carries_no_stage_31_token() -> None:
    inventory = (
        tuple(STAGE30_10_1_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_10_1_TEST_BASENAMES)
    )
    stage31_re = re.compile(r"stage_?31\b")
    for basename in inventory:
        assert stage31_re.search(basename.lower()) is None, (
            f"Stage 30.10.1 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )


# ---------------------------------------------------------------------------
# 11. No existing runtime / orchestrator / renderer / transport / Stage 28
#     suppression / manifest file imports the Stage 30.10.1 slice
# ---------------------------------------------------------------------------
#
# The Stage 30.10.1 eligibility model + classifier is a LEAF: nothing
# existing depends on it (it is NOT wired into the runtime yet). The runtime
# orchestrators, the compact renderer / models, the transport wrapper, and
# the Stage 30.1 tier projector must not reference either Stage 30.10.1
# module. (The Stage 30.10 manifest is intentionally excluded: it NAMES the
# Stage 30.10.1 basenames as constants-only data and is separately proven to
# import no PHX2 module.)


_FILES_THAT_MUST_NOT_IMPORT_THE_SLICE: Tuple[str, ...] = (
    "stage30_3_compact_runtime_session_orchestrator.py",
    "stage30_4_compact_runtime_session_orchestrator.py",
    "stage30_3_compact_body_transport_wrapper.py",
    "compact_ping_renderer.py",
    "compact_ping_models.py",
    "tier_decision_projector.py",
    "tier_decision_models.py",
)


def test_existing_files_do_not_import_the_slice() -> None:
    # "stage30_10_1_" is the shared prefix of both Stage 30.10.1 module
    # basenames, so this single needle catches an import of either.
    needle = "stage30_10_1_"
    for basename in _FILES_THAT_MUST_NOT_IMPORT_THE_SLICE:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"expected {path} to exist"
        text = path.read_text(encoding="utf-8")
        assert needle not in text, (
            f"{basename!r} must not reference a Stage 30.10.1 module "
            f"({needle!r}); the slice is a leaf and is not wired into the "
            f"runtime yet"
        )
