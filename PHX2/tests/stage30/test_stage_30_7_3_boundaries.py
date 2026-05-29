"""Stage 30.7.3 production-file boundary tests.

Scans the single Stage 30.7.3 production .py module (the offline sanitized
upstream ATH-evidence bridge) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses``),
  * a positive PHX2 import allowlist (only the Stage 30.7.1 closed-set
    models + the Stage 30.7.2 compact ATH runtime adapter) -- which proves,
    by construction, that NO Stage 21-29 / Stage 30.1-30.6 runtime / Discord
    / provider / network / disk module is imported (so NO compact renderer /
    models / orchestrator is imported and NO drawdown / tier recomputation
    is wired),
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` / ``os.environb``
    access,
  * no disk / storage surface import (``os`` / ``pathlib`` / ``shutil`` /
    ``sqlite3`` / zstd),
  * no network / secret module import,
  * no Stage 21-29 import and no PHX1 import (subsumes the Stage 25 / 27 / 28
    / 29 production must-not-import boundary -- no upstream module is
    importable at all),
  * no Discord / provider import surface,
  * no forbidden text needles (URL hosts, inbound-hook hosts, bearer
    tokens, API keys, RPC provider host forms),
  * no transport-construction / filesystem-write / network needles,
  * no compact renderer / models / orchestrator / tier-decision wiring
    needles (no drawdown / tier recomputation),
  * no ``open(`` call,
  * clean import.

Plus Stage 30.7.3 design pins: the bridge imports neither the compact
renderer nor the compact models; the renderer + models carry no Stage
30.7.3 wiring; the Stage 30.4.2 orchestrator was NOT edited by this slice
(the Stage 30.7.2 ``ath_context_resolver`` seam is reused); and the bridge
admits no Stage 30.7.4+ surface.

Fake / offline only. No live call, no provider, no Discord.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_7_manifest import (
    STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
    STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_MODULE,
    STAGE30_7_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_7_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME,
    STAGE30_7_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_3,
    STAGE30_7_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"

_ORCHESTRATOR_BASENAME: str = (
    "stage30_4_compact_runtime_session_orchestrator.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scanned_sources() -> Dict[str, str]:
    files: Dict[str, str] = {}
    for basename in STAGE30_7_3_SCANNED_PRODUCTION_BASENAMES:
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
# 1. Files exist + import cleanly
# ---------------------------------------------------------------------------


def test_all_production_files_exist() -> None:
    for basename in STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_3:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"Stage 30.7.3 requires {path}"


def test_scanned_production_basename_is_the_bridge() -> None:
    assert STAGE30_7_3_SCANNED_PRODUCTION_BASENAMES == (
        "stage30_7_sanitized_ath_bridge.py",
    )
    assert (
        STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME
        == "stage30_7_sanitized_ath_bridge.py"
    )


def test_production_module_imports_cleanly() -> None:
    import PHX2.stage30.stage30_7_sanitized_ath_bridge  # noqa: F401,E501


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
                module in STAGE30_7_3_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_7_3_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.7.3 module {filename!r} imports "
                f"non-allowlisted stdlib/3rd-party module {module!r}"
            )


def test_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_7_3_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.7.3 module {filename!r} imports "
                f"non-allowlisted PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_the_two_stage30_7_modules() -> None:
    # The bridge reads ONLY the Stage 30.7.1 models + the Stage 30.7.2
    # compact ATH runtime adapter (which wraps the Stage 30.7.1 projection);
    # it reaches no compact renderer / models / orchestrator and no
    # tier-decision module (so no drawdown / tier recomputation is
    # reachable), and no Stage 25 / 27 / 28 / 29 module.
    assert STAGE30_7_3_ALLOWED_PHX2_IMPORTS == (
        STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
        STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_MODULE,
    )
    for module in STAGE30_7_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_7_")


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.7.3 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.7.3 module {filename!r} imports {module!r}"
            )


def test_no_environ_access() -> None:
    for filename, text in _scanned_sources().items():
        tree = _module_ast(text)
        os_aliases: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        os_aliases.add(alias.asname or alias.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id in os_aliases
                    and node.attr in {"environ", "getenv", "environb"}
                ):
                    raise AssertionError(
                        f"Stage 30.7.3 module {filename!r} performs "
                        f"os.{node.attr} access"
                    )


# ---------------------------------------------------------------------------
# 4. No disk / storage / network / secret module imports
# ---------------------------------------------------------------------------


_FORBIDDEN_DISK_OR_STORAGE_MODULES: Tuple[str, ...] = (
    "os",
    "pathlib",
    "shutil",
    "sqlite3",
    "zstandard",
    "zstd",
    "lzma",
    "gzip",
    "zlib",
)


def test_no_disk_or_storage_surface_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_DISK_OR_STORAGE_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.7.3 module {filename!r} imports disk / "
                    f"storage surface module {module!r}"
                )


_FORBIDDEN_NETWORK_MODULES: Tuple[str, ...] = (
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
)


def test_no_network_or_secret_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.7.3 module {filename!r} imports "
                    f"network / secret module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / PHX1 import (subsumes the Stage 25/27/29 boundary)
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
                    f"Stage 30.7.3 module {filename!r} imports Stage "
                    f"21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.7.3 module {filename!r} imports PHX1 "
                f"module {module!r}"
            )


# ---------------------------------------------------------------------------
# 6. No Discord / provider import surface
# ---------------------------------------------------------------------------


_FORBIDDEN_PROVIDER_NEEDLES: Tuple[str, ...] = (
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
)


def test_no_provider_or_discord_import_surface() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if module.startswith("PHX2."):
                continue
            lower = module.lower()
            for needle in _FORBIDDEN_PROVIDER_NEEDLES:
                assert needle not in lower, (
                    f"Stage 30.7.3 module {filename!r} imports "
                    f"provider / Discord surface {needle!r}; offender "
                    f"{module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden text / transport / filesystem / network needles
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_7_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.7.3 module {filename!r} carries forbidden "
                f"text needle {needle!r}"
            )


def test_no_transport_or_filesystem_or_network_needles() -> None:
    needles = (
        # Transport construction.
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "requests." + "post",
        "requests." + "get",
        "ses" + "sion.post",
        "ses" + "sion.get",
        "client." + "post",
        "client." + "get",
        "url" + "open",
        "send_one_audited_post",
        # Filesystem write.
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
                f"Stage 30.7.3 module {filename!r} carries forbidden "
                f"transport / filesystem / network needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. No runtime wiring / no drawdown-tier recomputation needles
# ---------------------------------------------------------------------------
#
# The positive PHX2 import allowlist already proves (by construction) that
# the compact renderer / models / orchestrator / tier-decision modules are
# never imported. This source-text scan is the belt-and-suspenders proof
# that no wiring / recomputation symbol is referenced either. (The bare
# token ``drawdown_basis`` is read off the upstream shape as an INPUT alias;
# it is never a drawdown RECOMPUTATION, so the symbols scanned here are the
# renderer / orchestrator / tier-projector identifiers, not ``drawdown``.)


def test_no_runtime_wiring_or_recomputation_needles() -> None:
    needles = (
        "compact_ping_renderer",
        "compact_ping_models",
        "render_compact_ping",
        "compact_runtime_session_orchestrator",
        "compact_candidate_projection",
        "tier_decision_models",
        "tier_decision_projector",
        "TierDecisionRecord",
        "drawdown_from_ath",
    )
    for filename, text in _scanned_sources().items():
        for needle in needles:
            assert needle not in text, (
                f"Stage 30.7.3 module {filename!r} references runtime "
                f"wiring / recomputation symbol {needle!r}"
            )


# ---------------------------------------------------------------------------
# 9. No builtin open() call
# ---------------------------------------------------------------------------


def test_no_builtin_open_call() -> None:
    for filename, text in _scanned_sources().items():
        for node in ast.walk(_module_ast(text)):
            if isinstance(node, ast.Call) and isinstance(
                node.func, ast.Name
            ):
                assert node.func.id != "open", (
                    f"Stage 30.7.3 module {filename!r} calls builtin "
                    f"open()"
                )


# ---------------------------------------------------------------------------
# 10. The bridge does not import the compact renderer or models
# ---------------------------------------------------------------------------


def test_bridge_does_not_import_compact_renderer_or_models() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "PHX2.stage30.compact_ping_renderer" not in imports, (
            f"Stage 30.7.3 module {filename!r} must not import the "
            f"compact renderer"
        )
        assert "PHX2.stage30.compact_ping_models" not in imports, (
            f"Stage 30.7.3 module {filename!r} must not import the "
            f"compact models"
        )


# ---------------------------------------------------------------------------
# 11. Compact renderer + models carry no Stage 30.7.3 wiring (untouched)
# ---------------------------------------------------------------------------


def test_renderer_and_models_carry_no_stage30_7_3_wiring() -> None:
    for basename in (
        "compact_ping_renderer.py",
        "compact_ping_models.py",
    ):
        text = (STAGE30_ROOT / basename).read_text(encoding="utf-8")
        for needle in (
            "sanitized_ath_bridge",
            "Stage30_7_3",
            "stage30_7",
            "Stage30_7",
            "ath_context_resolver",
        ):
            assert needle not in text, (
                f"Stage 30.7.3 must not wire into {basename!r}; "
                f"found {needle!r}"
            )


# ---------------------------------------------------------------------------
# 12. The Stage 30.4.2 orchestrator was NOT edited by Stage 30.7.3
# ---------------------------------------------------------------------------


def test_orchestrator_not_edited_by_stage30_7_3() -> None:
    """The Stage 30.7.2 ``ath_context_resolver`` seam is reused as-is; Stage
    30.7.3 adds no reference to the bridge in the orchestrator, and the
    orchestrator still imports no Stage 30.7 module (duck-typed resolver
    only). The 30.7.2 ATH seam tokens may still be present (they are not a
    30.7.3 edit).
    """
    text = (STAGE30_ROOT / _ORCHESTRATOR_BASENAME).read_text(
        encoding="utf-8"
    )
    assert "sanitized_ath_bridge" not in text
    assert "Stage30_7_3" not in text
    assert "build_stage30_ath_resolver_from_sanitized_evidence" not in text
    for module in _imports_of(text):
        assert not module.startswith("PHX2.stage30.stage30_7"), (
            "Stage 30.4.2 orchestrator must still import no Stage 30.7 "
            f"module; offender {module!r}"
        )


# ---------------------------------------------------------------------------
# 13. The bridge admits no Stage 30.7.4+ surface
# ---------------------------------------------------------------------------


def test_bridge_admits_no_stage_30_7_4_surface() -> None:
    for _filename, text in _scanned_sources().items():
        for needle in ("30.7.4", "30_7_4", "Stage 30.7.4", "stage30_7_4"):
            assert needle not in text, (
                f"Stage 30.7.3 must not start / admit Stage 30.7.4; found "
                f"{needle!r}"
            )
    for basename in (
        STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_3
        + STAGE30_7_3_SCANNED_PRODUCTION_BASENAMES
    ):
        assert "7_4" not in basename


# ---------------------------------------------------------------------------
# 14. The bridge exposes its documented surface
# ---------------------------------------------------------------------------


def test_bridge_exposes_documented_surface() -> None:
    import PHX2.stage30.stage30_7_sanitized_ath_bridge as B

    assert callable(B.sanitized_ath_evidence_to_stage30_evidence)
    assert callable(B.sanitized_ath_evidence_to_compact_text)
    assert callable(B.build_stage30_ath_resolver_from_sanitized_evidence)
    assert callable(B.Stage30_7_3SanitizedUpstreamAthEvidence)
    assert B.STAGE30_7_3_MINOR_VERSION == "30.7.3"
    for name in (
        "STAGE30_7_3_MINOR_VERSION",
        "STAGE30_7_3_SOURCE_LABEL",
        "Stage30_7_3SanitizedUpstreamAthEvidence",
        "sanitized_ath_evidence_to_stage30_evidence",
        "sanitized_ath_evidence_to_compact_text",
        "build_stage30_ath_resolver_from_sanitized_evidence",
    ):
        assert name in B.__all__, (
            f"sanitized ATH bridge __all__ must export {name!r}"
        )
