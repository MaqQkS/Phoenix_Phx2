"""Stage 30.5.3 production-file boundary tests.

Scans the single Stage 30.5.3 production .py module (the offline Stage
29.5 migration-evidence bridge) for:

  * a positive stdlib import allowlist (only ``__future__`` / ``typing`` /
    ``dataclasses``),
  * a positive PHX2 import allowlist (only the Stage 30.5.1 models + the
    Stage 30.5.2 runtime display resolver) -- which proves, by
    construction, that NO Stage 29 / Stage 28 / Stage 30.1-30.4 / Discord /
    provider / network module is imported, and NO ATH / Net market-context
    model is reachable,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` / ``os.environb``
    access,
  * no network / secret module import,
  * no Stage 21-29 import and no PHX1 import (subsumes the Stage 29.5.5
    private side-channel renderer / recorder / artifact writer must-not-
    import boundary -- no Stage 29 module is importable at all),
  * no Discord / provider import surface,
  * no forbidden text needles (URL hosts, inbound-hook hosts, bearer
    tokens, API keys, RPC provider names),
  * no transport-construction needles,
  * clean import (no implicit network / env / filesystem I/O at import
    time).

Plus Stage 30.5.3 design pins: the bridge imports neither the compact
renderer nor the compact models; the renderer + models carry no Stage
30.5.3 wiring; the bridge introduces no ATH / Net field; the Stage 30.4.2
orchestrator was NOT edited by this slice (the Stage 30.5.2 resolver seam
is reused); and the bridge admits no Stage 30.5.4+ surface.

Fake / offline only. No live call.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_5_manifest import (
    STAGE30_5_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_5_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_5_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_5_3_STAGE29_MIGRATION_BRIDGE_BASENAME,
    STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_3,
    STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES,
    STAGE30_5_FORBIDDEN_TEXT_NEEDLES,
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
    for basename in STAGE30_5_3_SCANNED_PRODUCTION_BASENAMES:
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
    for basename in STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_3:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"Stage 30.5.3 requires {path}"


def test_scanned_production_basename_is_the_bridge() -> None:
    assert STAGE30_5_3_SCANNED_PRODUCTION_BASENAMES == (
        "stage30_5_stage29_migration_bridge.py",
    )
    assert (
        STAGE30_5_3_STAGE29_MIGRATION_BRIDGE_BASENAME
        == "stage30_5_stage29_migration_bridge.py"
    )


def test_production_module_imports_cleanly() -> None:
    import PHX2.stage30.stage30_5_stage29_migration_bridge  # noqa: F401,E501


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
                module in STAGE30_5_3_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_5_3_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.5.3 module {filename!r} imports non-allowlisted "
                f"stdlib/3rd-party module {module!r}"
            )


def test_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_5_3_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.5.3 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_the_two_stage30_5_modules() -> None:
    # The bridge reads ONLY the Stage 30.5.1 models + the Stage 30.5.2
    # runtime display resolver; it reaches no Stage 30.4 market-context
    # model (so no ATH / Net field is reachable) and no Stage 29 module.
    assert STAGE30_5_3_ALLOWED_PHX2_IMPORTS == (
        "PHX2.stage30.stage30_5_migration_context_models",
        "PHX2.stage30.stage30_5_compact_migration_runtime_adapter",
    )
    for module in STAGE30_5_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_5_")


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.5.3 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.5.3 module {filename!r} imports {module!r}"
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
                        f"Stage 30.5.3 module {filename!r} performs "
                        f"os.{node.attr} access"
                    )


# ---------------------------------------------------------------------------
# 4. No network module imports
# ---------------------------------------------------------------------------


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
    "json",
    "pathlib",
)


def test_no_network_or_secret_or_io_module_imports() -> None:
    # The bridge consumes an in-memory sanitized artifact-shaped input; it
    # uses no offline artifact reader, so it imports neither a network /
    # secret module NOR ``json`` / ``pathlib`` (no filesystem read/write).
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.5.3 module {filename!r} imports network / "
                    f"secret / I/O module {module!r}"
                )


# ---------------------------------------------------------------------------
# 5. No Stage 21-29 / PHX1 import (subsumes the Stage 29.5.5 boundary)
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
                    f"Stage 30.5.3 module {filename!r} imports Stage "
                    f"21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.5.3 module {filename!r} imports PHX1 module "
                f"{module!r}"
            )


def test_no_stage29_5_5_side_channel_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        for forbidden in STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES:
            assert forbidden not in imports, (
                f"Stage 30.5.3 module {filename!r} imports forbidden "
                f"Stage 29.5.5 side-channel module"
            )


# ---------------------------------------------------------------------------
# 6. No Discord / provider import surface (non-PHX2 import targets)
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
                    f"Stage 30.5.3 module {filename!r} imports provider / "
                    f"Discord surface {needle!r}; offender {module!r}"
                )


# ---------------------------------------------------------------------------
# 7. No forbidden text needles / transport-construction needles
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles() -> None:
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in STAGE30_5_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lower, (
                f"Stage 30.5.3 module {filename!r} carries forbidden "
                f"text needle {needle!r}"
            )


def test_no_transport_construction_needles() -> None:
    needles = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "ses" + "sion.post",
        "ses" + "sion.get",
        "requests." + "post",
        "requests." + "get",
        "client." + "post",
        "client." + "get",
        "url" + "open",
        "send_one_audited_post",
    )
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in needles:
            assert needle.lower() not in lower, (
                f"Stage 30.5.3 module {filename!r} carries transport-"
                f"construction needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. The bridge does not import the compact renderer or models
# ---------------------------------------------------------------------------


def test_bridge_does_not_import_compact_renderer_or_models() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert (
            "PHX2.stage30.compact_ping_renderer" not in imports
        ), (
            f"Stage 30.5.3 module {filename!r} must not import the compact "
            f"renderer"
        )
        assert "PHX2.stage30.compact_ping_models" not in imports, (
            f"Stage 30.5.3 module {filename!r} must not import the compact "
            f"models"
        )


# ---------------------------------------------------------------------------
# 9. Compact renderer + models carry no Stage 30.5.3 wiring (untouched)
# ---------------------------------------------------------------------------


def test_renderer_and_models_carry_no_stage30_5_wiring() -> None:
    for basename in (
        "compact_ping_renderer.py",
        "compact_ping_models.py",
    ):
        text = (STAGE30_ROOT / basename).read_text(encoding="utf-8")
        for needle in (
            "stage30_5",
            "Stage30_5",
            "stage29_migration_bridge",
            "migration_context_resolver",
        ):
            assert needle not in text, (
                f"Stage 30.5.3 must not wire into {basename!r}; "
                f"found {needle!r}"
            )


# ---------------------------------------------------------------------------
# 10. The Stage 30.4.2 orchestrator was NOT edited by Stage 30.5.3
# ---------------------------------------------------------------------------


def test_orchestrator_not_edited_by_stage30_5_3() -> None:
    """The Stage 30.5.2 resolver seam is reused as-is; Stage 30.5.3 adds no
    reference to the bridge in the orchestrator, and the orchestrator still
    imports no Stage 30.5 module (duck-typed resolver only).
    """
    text = (STAGE30_ROOT / _ORCHESTRATOR_BASENAME).read_text(
        encoding="utf-8"
    )
    assert "stage29_migration_bridge" not in text
    assert "Stage30_5_3" not in text
    for module in _imports_of(text):
        assert not module.startswith("PHX2.stage30.stage30_5"), (
            "Stage 30.4.2 orchestrator must still import no Stage 30.5 "
            f"module; offender {module!r}"
        )


# ---------------------------------------------------------------------------
# 11. The bridge introduces no ATH / Net field
# ---------------------------------------------------------------------------


def test_bridge_introduces_no_ath_or_net_field() -> None:
    from PHX2.stage30.stage30_5_migration_context_models import (
        projection_field_names,
        record_field_names,
    )
    from PHX2.stage30.stage30_5_stage29_migration_bridge import (
        Stage30_5_3SanitizedStage29MigrationEvidence,
    )

    sanitized_fields = {
        f.name
        for f in dataclasses.fields(
            Stage30_5_3SanitizedStage29MigrationEvidence
        )
    }
    all_field_names = (
        tuple(sanitized_fields)
        + record_field_names()
        + projection_field_names()
    )
    for name in all_field_names:
        lower = name.lower()
        assert "ath" not in lower, (
            f"Stage 30.5.3 must introduce no ATH field; found {name!r}"
        )
        assert "net" not in lower, (
            f"Stage 30.5.3 must introduce no Net field; found {name!r}"
        )


# ---------------------------------------------------------------------------
# 12. The bridge admits no Stage 30.5.4+ surface
# ---------------------------------------------------------------------------


def test_bridge_admits_no_stage_30_5_4_surface() -> None:
    for _filename, text in _scanned_sources().items():
        for needle in ("30.5.4", "30_5_4", "Stage 30.5.4", "stage30_5_4"):
            assert needle not in text, (
                f"Stage 30.5.3 must not start / admit Stage 30.5.4; found "
                f"{needle!r}"
            )
    for basename in (
        STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_3
        + STAGE30_5_3_SCANNED_PRODUCTION_BASENAMES
    ):
        assert "5_4" not in basename
