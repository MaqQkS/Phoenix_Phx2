"""Stage 30.5.2 production-file boundary tests.

Scans the single Stage 30.5.2 production .py module (the offline
compact migration runtime adapter) for:

  * a positive stdlib import allowlist (only ``__future__`` /
    ``typing``),
  * a positive PHX2 import allowlist (only the two Stage 30.5.1
    sibling modules: the projector + the closed-set display
    vocabulary) -- which proves, by construction, that NO Stage 29 /
    Stage 28 / Stage 30.1-30.4 / Discord / provider / network module
    is imported, and NO ATH / Net market-context model is reachable,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` /
    ``os.environb`` access,
  * no network module import,
  * no Stage 21-29 import and no PHX1 import (subsumes the Stage
    29.5.5 private side-channel renderer / recorder / artifact writer
    must-not-import boundary),
  * no Discord / provider import surface,
  * no forbidden text needles (URL hosts, inbound-hook hosts, bearer
    tokens, API keys, RPC provider names),
  * no transport-construction needles,
  * clean import (no implicit network / env / filesystem I/O at
    import time).

Plus a Stage 30.5.2 design pin: the Stage 30.4.2 orchestrator that
consumes the migration display resolver imports NO Stage 30.5 module
(the resolver is consumed through a duck-typed ``object`` parameter),
and the runtime adapter's display vocabulary never leaves the three
closed-set migration words.

Fake / offline only. No live call.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional, Set, Tuple

from PHX2.stage30.stage30_5_manifest import (
    STAGE30_5_2_ALLOWED_PHX2_IMPORTS,
    STAGE30_5_2_ALLOWED_STDLIB_IMPORTS,
    STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME,
    STAGE30_5_2_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_2,
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
    for basename in STAGE30_5_2_SCANNED_PRODUCTION_BASENAMES:
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
    for basename in STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_2:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"Stage 30.5.2 requires {path}"


def test_scanned_production_basename_is_the_runtime_adapter() -> None:
    assert STAGE30_5_2_SCANNED_PRODUCTION_BASENAMES == (
        "stage30_5_compact_migration_runtime_adapter.py",
    )
    assert (
        STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME
        == "stage30_5_compact_migration_runtime_adapter.py"
    )


def test_production_module_imports_cleanly() -> None:
    import PHX2.stage30.stage30_5_compact_migration_runtime_adapter  # noqa: F401,E501


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
                module in STAGE30_5_2_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_5_2_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.5.2 module {filename!r} imports non-allowlisted "
                f"stdlib/3rd-party module {module!r}"
            )


def test_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_5_2_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.5.2 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


def test_phx2_allowlist_is_the_two_stage30_5_1_modules() -> None:
    # The runtime adapter reads ONLY the Stage 30.5.1 projector + models;
    # it reaches no Stage 30.4 market-context model (so no ATH / Net
    # field is reachable) and no Stage 30.2 / 30.3 / 30.4 runtime module.
    assert STAGE30_5_2_ALLOWED_PHX2_IMPORTS == (
        "PHX2.stage30.stage30_5_migration_context_adapter",
        "PHX2.stage30.stage30_5_migration_context_models",
    )
    for module in STAGE30_5_2_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_5_")


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.5.2 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.5.2 module {filename!r} imports {module!r}"
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
                        f"Stage 30.5.2 module {filename!r} performs "
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
)


def test_no_network_or_secret_module_imports() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            for forbidden in _FORBIDDEN_NETWORK_MODULES:
                assert not (
                    module == forbidden
                    or module.startswith(forbidden + ".")
                ), (
                    f"Stage 30.5.2 module {filename!r} imports network / "
                    f"secret module {module!r}"
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
                    f"Stage 30.5.2 module {filename!r} imports Stage "
                    f"21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.5.2 module {filename!r} imports PHX1 module "
                f"{module!r}"
            )


def test_no_stage29_5_5_side_channel_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        for forbidden in STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES:
            assert forbidden not in imports, (
                f"Stage 30.5.2 module {filename!r} imports forbidden "
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
                    f"Stage 30.5.2 module {filename!r} imports provider / "
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
                f"Stage 30.5.2 module {filename!r} carries forbidden "
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
                f"Stage 30.5.2 module {filename!r} carries transport-"
                f"construction needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. Stage 30.4.2 orchestrator stays import-pure (duck-typed resolver)
# ---------------------------------------------------------------------------


def test_orchestrator_imports_no_stage30_5_module() -> None:
    """The Stage 30.4.2 orchestrator consumes the Stage 30.5.2 migration
    display resolver through a duck-typed ``object`` parameter, so the
    orchestrator file must import NO Stage 30.5 module. This keeps the
    Stage 30.4.2 read-only import allowlist intact.
    """
    orchestrator_text = (
        STAGE30_ROOT / _ORCHESTRATOR_BASENAME
    ).read_text(encoding="utf-8")
    for module in _imports_of(orchestrator_text):
        assert not module.startswith("PHX2.stage30.stage30_5"), (
            "Stage 30.4.2 orchestrator must not import any Stage 30.5 "
            f"module (duck-typed resolver only); offender {module!r}"
        )


def test_orchestrator_threads_the_migration_resolver_param() -> None:
    """The Stage 30.4.2 orchestrator + wrapper reference the opt-in
    ``migration_context_resolver`` seam (a positive presence pin so a
    future refactor cannot silently drop the Stage 30.5.2 wiring).
    """
    orchestrator_text = (
        STAGE30_ROOT / _ORCHESTRATOR_BASENAME
    ).read_text(encoding="utf-8")
    assert "migration_context_resolver" in orchestrator_text
    assert "resolve_display_text" in orchestrator_text


def test_orchestrator_carries_local_closed_set_migration_guard() -> None:
    """The Stage 30.4.2 runtime seam pins a LOCAL closed-set guard (a
    plain tuple literal, NOT a Stage 30.5 import) so a duck-typed
    resolver can only inject ``Known`` / ``Unverified`` / ``Unknown``
    into the ``Mig`` token. No off-vocabulary ``Mig: Stale`` /
    ``Mig: Fresh`` rendered form ever appears in the orchestrator.
    """
    orchestrator_text = (
        STAGE30_ROOT / _ORCHESTRATOR_BASENAME
    ).read_text(encoding="utf-8")
    assert (
        "_STAGE30_5_2_ALLOWED_MIGRATION_DISPLAY_WORDS" in orchestrator_text
    )
    assert "Mig: Stale" not in orchestrator_text
    assert "Mig: Fresh" not in orchestrator_text


# ---------------------------------------------------------------------------
# 9. Stage 30.2 renderer / models carry no Stage 30.5.2 wiring (the Mig
#    token is filled via the existing migration_mc_text slot; the renderer
#    and models were NOT edited by this slice)
# ---------------------------------------------------------------------------


def test_renderer_and_models_carry_no_stage30_5_2_wiring() -> None:
    for basename in (
        "compact_ping_renderer.py",
        "compact_ping_models.py",
    ):
        text = (STAGE30_ROOT / basename).read_text(encoding="utf-8")
        for needle in (
            "migration_context_resolver",
            "resolve_display_text",
            "stage30_5",
            "Stage30_5",
            "_STAGE30_5_2_ALLOWED_MIGRATION_DISPLAY_WORDS",
        ):
            assert needle not in text, (
                f"Stage 30.5.2 must not wire into {basename!r}; "
                f"found {needle!r}"
            )


# ---------------------------------------------------------------------------
# 10. Runtime adapter display vocabulary is the closed set (no ATH / Net /
#    Fresh / Stale word introduced)
# ---------------------------------------------------------------------------


class _FakeRaisingSource:
    def read(
        self,
        token_mint: str,
        observed_at_utc: Optional[str] = None,
    ) -> object:
        raise RuntimeError("boom")


def test_runtime_adapter_display_vocabulary_is_closed_set() -> None:
    from PHX2.stage30.stage30_5_compact_migration_runtime_adapter import (
        resolve_migration_display_text,
    )
    from PHX2.stage30.stage30_5_migration_context_models import (
        MIGRATION_BASIS_ON_CHAIN_EVENT,
        MIGRATION_DISPLAY_VALUES,
        MIGRATION_STATUS_KNOWN,
        SOURCE_REASON_SOURCE_PRESENT,
        SOURCE_STATUS_PRESENT,
        STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
        Stage30_5MigrationContextRecord,
    )

    present_known = Stage30_5MigrationContextRecord(
        schema_version=STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
        token_label=None,
        migration_status=MIGRATION_STATUS_KNOWN,
        migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
        migration_event_time_utc=None,
        migration_age_seconds=None,
        source_label="stage30_5_2_boundary_fake",
        source_status=SOURCE_STATUS_PRESENT,
        source_reason=SOURCE_REASON_SOURCE_PRESENT,
        runtime_consumable=False,
        observed_at_utc="2026-05-29T00:00:00Z",
    )

    observed = {
        resolve_migration_display_text(
            SimpleNamespace(read=lambda m, o=None: present_known),
            "FakeMintForBoundaryStage305_2Base5822222222",
            "2026-05-29T00:00:00Z",
        ),
        resolve_migration_display_text(
            None, "FakeMintForBoundaryStage305_2Base5822222222", None
        ),
        resolve_migration_display_text(
            _FakeRaisingSource(),
            "FakeMintForBoundaryStage305_2Base5822222222",
            None,
        ),
    }
    assert observed <= set(MIGRATION_DISPLAY_VALUES)
    assert observed <= {"Known", "Unverified", "Unknown"}
    assert "Fresh" not in observed
    assert "Stale" not in observed


def test_adapter_exposes_documented_surface() -> None:
    import PHX2.stage30.stage30_5_compact_migration_runtime_adapter as M

    assert callable(M.resolve_migration_display_text)
    assert callable(M.Stage30_5_2MigrationDisplayResolver)
    assert M.STAGE30_5_2_MINOR_VERSION == "30.5.2"
    for name in (
        "STAGE30_5_2_MINOR_VERSION",
        "resolve_migration_display_text",
        "Stage30_5_2MigrationDisplayResolver",
    ):
        assert name in M.__all__, (
            f"runtime adapter __all__ must export {name!r}"
        )
