"""Stage 30.7.1 production-file boundary tests.

Scans the two Stage 30.7.1 production .py modules (ATH context models
+ pure projection adapter) for:

  * a positive stdlib import allowlist (only ``__future__`` /
    ``typing`` / ``dataclasses`` / ``decimal`` / ``math`` / ``re``),
  * a positive PHX2 import allowlist (only the Stage 30.7.1 models
    sibling) -- which proves, by construction, that NO Stage 21-29 /
    Stage 30.1-30.6 runtime / Discord / provider / network / disk
    module is imported (so NO compact renderer / models / orchestrator
    is imported and NO drawdown / tier recomputation is wired),
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` /
    ``os.environb`` access,
  * no disk / storage surface import (``os`` / ``pathlib`` /
    ``shutil`` / ``sqlite3`` / zstd),
  * no network module import,
  * no Stage 21-29 import and no PHX1 import (subsumes the Stage 29.5
    production must-not-import boundary),
  * no Discord / provider import surface,
  * no forbidden text needles (URL hosts, inbound-hook hosts, bearer
    tokens, API keys, RPC provider names),
  * no transport-construction / filesystem-write / network needles,
  * no compact renderer / models / orchestrator / tier-decision wiring
    needles (no ATH runtime wiring, no drawdown / tier recomputation),
  * no ``open(`` call,
  * clean import.

Fake / offline only. No live call, no provider, no Discord.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_7_manifest import (
    STAGE30_7_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_7_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME,
    STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME,
    STAGE30_7_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_1,
    STAGE30_7_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scanned_sources() -> Dict[str, str]:
    files: Dict[str, str] = {}
    for basename in STAGE30_7_1_SCANNED_PRODUCTION_BASENAMES:
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
    for basename in STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_1:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"Stage 30.7.1 requires {path}"


def test_scanned_production_basenames_are_the_two_modules() -> None:
    assert STAGE30_7_1_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME,
        STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME,
    )


def test_every_production_module_imports_cleanly() -> None:
    import PHX2.stage30.stage30_7_ath_context_models  # noqa: F401
    import PHX2.stage30.stage30_7_ath_context_projection  # noqa: F401


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
                module in STAGE30_7_1_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_7_1_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.7.1 module {filename!r} imports "
                f"non-allowlisted stdlib/3rd-party module {module!r}"
            )


def test_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_7_1_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.7.1 module {filename!r} imports "
                f"non-allowlisted PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_only_the_models_sibling() -> None:
    assert STAGE30_7_1_ALLOWED_PHX2_IMPORTS == (
        STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
    )
    for module in STAGE30_7_1_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_7_")


def test_models_module_imports_no_phx2_module() -> None:
    text = (
        STAGE30_ROOT / STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME
    ).read_text(encoding="utf-8")
    phx2_imports = {
        module
        for module in _imports_of(text)
        if module.startswith("PHX2.")
    }
    assert phx2_imports == set(), (
        "Stage 30.7.1 models module must import no PHX2 module; "
        f"found {sorted(phx2_imports)}"
    )


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.7.1 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.7.1 module {filename!r} imports {module!r}"
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
                        f"Stage 30.7.1 module {filename!r} performs "
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
                    f"Stage 30.7.1 module {filename!r} imports disk / "
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
                    f"Stage 30.7.1 module {filename!r} imports "
                    f"network / secret module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / PHX1 import (subsumes the Stage 29.5 boundary)
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
                    f"Stage 30.7.1 module {filename!r} imports Stage "
                    f"21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.7.1 module {filename!r} imports PHX1 "
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
                    f"Stage 30.7.1 module {filename!r} imports "
                    f"provider / Discord surface {needle!r}; offender "
                    f"{module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden text / transport / network needles
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_7_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.7.1 module {filename!r} carries forbidden "
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
                f"Stage 30.7.1 module {filename!r} carries forbidden "
                f"transport / filesystem / network needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. No ATH runtime wiring / no drawdown-tier recomputation needles
# ---------------------------------------------------------------------------
#
# The positive PHX2 import allowlist already proves (by construction)
# that the compact renderer / models / orchestrator / tier-decision
# modules are never imported. This source-text scan is the belt-and-
# suspenders proof that no wiring symbol is referenced either. (The
# bare words ``tier`` / ``drawdown`` are deliberately NOT scanned --
# the projection legitimately documents that it recomputes NO tier /
# drawdown and carries a ``should_trust_for_drawdown`` provenance flag;
# the specific wiring module / function names below are what would
# indicate an actual wiring / recomputation.)


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
    )
    for filename, text in _scanned_sources().items():
        for needle in needles:
            assert needle not in text, (
                f"Stage 30.7.1 module {filename!r} references runtime "
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
                    f"Stage 30.7.1 module {filename!r} calls builtin "
                    f"open()"
                )


# ---------------------------------------------------------------------------
# 10. Production module-source guards exposed
# ---------------------------------------------------------------------------


def test_models_exposes_forbidden_field_name_guard() -> None:
    from PHX2.stage30.stage30_7_ath_context_models import (
        FORBIDDEN_RECORD_FIELD_NAMES,
        is_forbidden_record_field_name,
    )

    assert callable(is_forbidden_record_field_name)
    assert len(FORBIDDEN_RECORD_FIELD_NAMES) >= 20
    assert is_forbidden_record_field_name("raw_payload")
    assert not is_forbidden_record_field_name("ath_value")


def test_projection_exposes_project_function() -> None:
    from PHX2.stage30.stage30_7_ath_context_projection import (
        project_ath_context,
    )

    assert callable(project_ath_context)
