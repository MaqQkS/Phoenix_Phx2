"""Stage 30.9.3 dip-filtered live gate integration boundary tests.

Scans the four Stage 30.9.3 production .py modules (the integration models, the
adapter, the orchestrator, the fake integration proof) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses`` / ``decimal``),
  * a positive PHX2 import allowlist (the Stage 30.9.3 own models + adapter +
    orchestrator siblings plus the committed Stage 30.10 dip-gate stack
    modules) -- which proves, by construction, that NO Stage 21-29 (incl. Stage
    28 suppression / Stage 29.5) / Stage 30.3 / Stage 30.4 runtime orchestrator
    / renderer / transport / Discord / provider / network module is imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` access,
  * no database / SQLite / compression surface import,
  * no network / secret / subprocess / threading / async / time import,
  * no Stage 21-29 / Stage 29.5 / PHX1 import,
  * no forbidden secret / transport / URL text needle and no ``://`` literal,
  * no public / subscriber / paid / Telegram / social / trading / wallet /
    enforcement term,
  * no transport-veto / dispatch-failure / ``PAYLOAD_REFUSED`` flag ever set to
    ``True`` for a candidate,
  * no filesystem write surface,
  * no implicit I/O at import time (zero top-level Call nodes),
  * no Stage 30.9.4+ / Stage 30.10.4+ / Stage 31 file admitted by the manifest
    inventory, and
  * no existing runtime orchestrator / renderer / transport / Stage 28
    suppression / Stage 30.1 projector / Stage 30.9.1 bridge / Stage 30.9.2
    resume / Stage 30.10.x module imports the Stage 30.9.3 slice (the slice is a
    leaf; nothing existing depends on it, and it is NOT wired into the runtime
    yet).

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_9_manifest import (
    STAGE30_9_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_9_3_ALLOWED_STAGE30_BASENAMES,
    STAGE30_9_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_9_3_GATE_ADAPTER_BASENAME,
    STAGE30_9_3_GATE_ADAPTER_MODULE,
    STAGE30_9_3_GATE_MODELS_BASENAME,
    STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME,
    STAGE30_9_3_GATE_ORCHESTRATOR_MODULE,
    STAGE30_9_3_FAKE_PROOF_BASENAME,
    STAGE30_9_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_9_3_STAGE30_10_1_MODELS_MODULE,
    STAGE30_9_3_STAGE30_10_2_GATE_MODELS_MODULE,
    STAGE30_9_3_STAGE30_10_2_GATE_MODULE,
    STAGE30_9_3_STAGE30_10_3_ARTIFACT_MODELS_MODULE,
    STAGE30_9_3_STAGE30_10_3_PROJECTOR_MODULE,
    STAGE30_9_3_TEST_BASENAMES,
    STAGE30_9_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _source_of(basename: str) -> str:
    return (STAGE30_ROOT / basename).read_text(encoding="utf-8")


def _scanned_sources() -> Dict[str, str]:
    return {
        basename: _source_of(basename)
        for basename in STAGE30_9_3_SCANNED_PRODUCTION_BASENAMES
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
    for basename in STAGE30_9_3_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.9.3 requires {basename}"
        )


def test_scanned_basenames_are_the_four_modules() -> None:
    assert STAGE30_9_3_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_9_3_GATE_MODELS_BASENAME,
        STAGE30_9_3_GATE_ADAPTER_BASENAME,
        STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME,
        STAGE30_9_3_FAKE_PROOF_BASENAME,
    )


def test_modules_import_cleanly() -> None:
    import PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models  # noqa: F401
    import PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter  # noqa: F401
    import PHX2.stage30.stage30_9_3_dip_filtered_live_gate_orchestrator  # noqa: F401,E501
    import PHX2.stage30.stage30_9_3_fake_live_gate_integration_proof  # noqa: F401,E501


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
                module in STAGE30_9_3_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_9_3_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.9.3 module {filename!r} imports non-allowlisted "
                f"stdlib / third-party module {module!r}"
            )


def test_stdlib_allowlist_excludes_io_and_db_surfaces() -> None:
    for forbidden in ("os", "json", "pathlib", "sqlite3", "zstandard"):
        assert forbidden not in STAGE30_9_3_ALLOWED_STDLIB_IMPORTS


def test_all_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_9_3_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.9.3 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_models_phx2_imports_are_empty() -> None:
    phx2 = _phx2_imports_of(STAGE30_9_3_GATE_MODELS_BASENAME)
    assert phx2 == set(), (
        "Stage 30.9.3 integration models must import no PHX2 module; found "
        f"{sorted(phx2)}"
    )


def test_adapter_phx2_imports_are_the_models_plus_gate_stack() -> None:
    phx2 = _phx2_imports_of(STAGE30_9_3_GATE_ADAPTER_BASENAME)
    assert phx2 == {
        STAGE30_9_3_GATE_MODELS_MODULE,
        STAGE30_9_3_STAGE30_10_1_MODELS_MODULE,
        STAGE30_9_3_STAGE30_10_2_GATE_MODULE,
        STAGE30_9_3_STAGE30_10_2_GATE_MODELS_MODULE,
        STAGE30_9_3_STAGE30_10_3_ARTIFACT_MODELS_MODULE,
        STAGE30_9_3_STAGE30_10_3_PROJECTOR_MODULE,
    }, (
        "Stage 30.9.3 adapter must import the Stage 30.9.3 models sibling plus "
        f"the committed Stage 30.10 dip-gate stack; found {sorted(phx2)}"
    )


def test_orchestrator_phx2_imports_are_models_adapter_and_gate_tokens() -> None:
    phx2 = _phx2_imports_of(STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME)
    assert phx2 == {
        STAGE30_9_3_GATE_MODELS_MODULE,
        STAGE30_9_3_GATE_ADAPTER_MODULE,
        STAGE30_9_3_STAGE30_10_1_MODELS_MODULE,
        STAGE30_9_3_STAGE30_10_2_GATE_MODELS_MODULE,
    }, (
        "Stage 30.9.3 orchestrator must import the Stage 30.9.3 models + "
        f"adapter siblings plus the gate-decision tokens; found {sorted(phx2)}"
    )


def test_proof_phx2_imports_are_models_and_orchestrator() -> None:
    phx2 = _phx2_imports_of(STAGE30_9_3_FAKE_PROOF_BASENAME)
    assert phx2 == {
        STAGE30_9_3_GATE_MODELS_MODULE,
        STAGE30_9_3_GATE_ORCHESTRATOR_MODULE,
    }, (
        "Stage 30.9.3 fake proof must import the Stage 30.9.3 models + "
        f"orchestrator siblings; found {sorted(phx2)}"
    )


def test_phx2_allowlist_stays_within_stage30_family() -> None:
    for module in STAGE30_9_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_9_3_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "transport", "suppress", "renderer"):
        # The Stage 30.9.3 orchestrator module name legitimately carries the
        # word "orchestrator"; every OTHER forbidden surface must be absent.
        if forbidden == "orchestrator":
            continue
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.9.3 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.9.3 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "environb"), (
                    f"Stage 30.9.3 module {filename!r} performs "
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
                    f"Stage 30.9.3 module {filename!r} imports database / "
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
                    f"Stage 30.9.3 module {filename!r} imports forbidden "
                    f"network / secret / concurrency module {module!r}"
                )


def test_no_sleep_call_surface() -> None:
    for filename, text in _scanned_sources().items():
        assert "sleep(" not in text, (
            f"Stage 30.9.3 module {filename!r} carries a sleep call surface"
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
                    f"Stage 30.9.3 module {filename!r} imports Stage 21-29 "
                    f"module {module!r}"
                )
            assert "stage28" not in module, (
                f"Stage 30.9.3 module {filename!r} imports Stage 28 module "
                f"{module!r}"
            )
            assert "stage29" not in module, (
                f"Stage 30.9.3 module {filename!r} imports Stage 29 module "
                f"{module!r}"
            )
            assert not module.startswith("PHX1"), (
                f"Stage 30.9.3 module {filename!r} imports PHX1 module "
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
)


def test_no_provider_runtime_or_transport_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module in STAGE30_9_3_ALLOWED_PHX2_IMPORTS:
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_IMPORT_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.9.3 module {filename!r} imports forbidden "
                    f"surface {needle!r}; offender {module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden secret / transport / URL text needles + no transport scheme
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_9_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.9.3 module {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_no_transport_scheme_literal() -> None:
    for filename, text in _scanned_sources().items():
        assert "://" not in text, (
            f"Stage 30.9.3 module {filename!r} carries a transport scheme "
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
                f"Stage 30.9.3 module {filename!r} carries forbidden "
                f"surface term {term!r}"
            )


# ---------------------------------------------------------------------------
# 9. No transport-safety flag ever set True; no filesystem write
# ---------------------------------------------------------------------------


def _whitespace_stripped(text: str) -> str:
    return "".join(text.split())


def test_transport_safety_flags_are_never_set_true() -> None:
    for filename, text in _scanned_sources().items():
        stripped = _whitespace_stripped(text)
        for flag in (
            "dispatch_failure_recorded",
            "transport_veto_used",
            "payload_refused_used",
            "dispatch_failures_recorded",
            "transport_veto_count",
            "payload_refused_count",
        ):
            assert f"{flag}=True" not in stripped, (
                f"Stage 30.9.3 module {filename!r} sets {flag}=True; the "
                "dip-filtered seam must never record a dispatch failure / "
                "transport veto / PAYLOAD_REFUSED"
            )


def test_no_filesystem_write_surface() -> None:
    for filename, text in _scanned_sources().items():
        for needle in ("open(", "Path(", ".write_text(", ".write_bytes("):
            assert needle not in text, (
                f"Stage 30.9.3 module {filename!r} carries a filesystem "
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
            f"Stage 30.9.3 module {filename!r} carries an unexpected "
            f"top-level call (implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# 11. No Stage 30.9.4+ / Stage 30.10.4+ / Stage 31 file admitted by inventory
# ---------------------------------------------------------------------------


_STAGE_30_9_MINOR_RE = re.compile(r"stage_?30_9_(\d+)")
_STAGE_30_10_MINOR_RE = re.compile(r"stage_?30_10_(\d+)")
_STAGE_31_RE = re.compile(r"stage_?31\b")


def test_inventory_admits_no_stage_30_9_4_plus_file() -> None:
    inventory = (
        tuple(STAGE30_9_3_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_9_3_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_9_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 4:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.9.3 inventory must not admit a Stage 30.9.4+ file yet; "
        f"saw {violations!r}"
    )


def test_inventory_admits_no_stage_30_10_4_plus_or_stage_31_file() -> None:
    inventory = (
        tuple(STAGE30_9_3_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_9_3_TEST_BASENAMES)
    )
    for basename in inventory:
        lowered = basename.lower()
        for match in _STAGE_30_10_MINOR_RE.finditer(lowered):
            assert int(match.group(1)) <= 3, (
                "Stage 30.9.3 inventory must not admit a Stage 30.10.4+ file; "
                f"offender {basename!r}"
            )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 30.9.3 inventory must carry no Stage 31 token; offender "
            f"{basename!r}"
        )


# ---------------------------------------------------------------------------
# 12. No existing runtime / orchestrator / transport / Stage 28 suppression /
#     Stage 30.1 projector / Stage 30.9.1 / 30.9.2 / 30.10.x file imports the
#     Stage 30.9.3 slice
# ---------------------------------------------------------------------------
#
# The Stage 30.9.3 slice is a LEAF: it COMPOSES the committed Stage 30.10
# dip-gate stack, and nothing existing depends on it (it is NOT wired into the
# runtime yet). The runtime orchestrators, the compact renderer / models, the
# transport wrapper, the Stage 30.1 tier projector, the Stage 30.9.1 bridge
# modules, the Stage 30.9.2 resume modules, AND the Stage 30.10.x modules (which
# the slice depends on, not the other way round) must not reference any Stage
# 30.9.3 module. (The Stage 30.9 manifest is intentionally excluded: it NAMES
# the Stage 30.9.3 basenames as constants-only data and imports no PHX2 module.)


_FILES_THAT_MUST_NOT_IMPORT_THE_SLICE: Tuple[str, ...] = (
    "stage30_3_compact_runtime_session_orchestrator.py",
    "stage30_4_compact_runtime_session_orchestrator.py",
    "stage30_3_compact_body_transport_wrapper.py",
    "compact_ping_renderer.py",
    "compact_ping_models.py",
    "tier_decision_projector.py",
    "tier_decision_models.py",
    "stage30_9_artifact_bridge_models.py",
    "stage30_9_capture_transport.py",
    "stage30_9_artifact_projector.py",
    "stage30_9_artifact_bridge_proof.py",
    "stage30_9_2_resume_dip_filtered_live_models.py",
    "stage30_9_2_resume_dip_filtered_live_plan.py",
    "stage30_9_2_resume_fake_proof.py",
    "stage30_10_1_tier_dip_eligibility_models.py",
    "stage30_10_1_tier_dip_eligibility_classifier.py",
    "stage30_10_2_pre_dispatch_gate_models.py",
    "stage30_10_2_pre_dispatch_gate.py",
    "stage30_10_2_fake_gate_proof.py",
    "stage30_10_3_gate_artifact_models.py",
    "stage30_10_3_gate_artifact_projector.py",
    "stage30_10_3_fake_artifact_proof.py",
)


def test_existing_files_do_not_import_the_slice() -> None:
    # "stage30_9_3_" is the shared prefix of all four Stage 30.9.3 module
    # basenames, so this single needle catches an import of any of them.
    needle = "stage30_9_3_"
    for basename in _FILES_THAT_MUST_NOT_IMPORT_THE_SLICE:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"expected {path} to exist"
        text = path.read_text(encoding="utf-8")
        assert needle not in text, (
            f"{basename!r} must not reference a Stage 30.9.3 module "
            f"({needle!r}); the slice is a leaf and is not wired into the "
            f"runtime yet"
        )
