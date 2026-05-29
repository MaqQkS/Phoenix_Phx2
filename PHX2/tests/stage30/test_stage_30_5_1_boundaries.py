"""Stage 30.5.1 production-file boundary tests.

Scans the three Stage 30.5.1 production .py modules (models, source
protocol, adapter) for:

  * a positive stdlib import allowlist (only ``__future__`` /
    ``typing`` / ``dataclasses`` / ``re``),
  * a positive PHX2 import allowlist (only the three Stage 30.5.1
    sibling modules) -- which proves, by construction, that NO Stage
    29 / Stage 28 / Stage 30.1-30.4 / Discord / provider / network
    module is imported,
  * no ``os`` import and no ``os.environ`` / ``os.getenv`` /
    ``os.environb`` access,
  * no network module import,
  * no Stage 21-29 import and no PHX1 import (subsumes the Stage
    29.5.5 private side-channel renderer / recorder / artifact
    writer must-not-import boundary),
  * no Discord / provider import surface,
  * no forbidden text needles (URL hosts, inbound-hook hosts, bearer
    tokens, API keys, RPC provider names),
  * no transport-construction needles,
  * clean import (no implicit network / env / filesystem I/O at
    import time).

Fake / offline only. No live call.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set, Tuple

from PHX2.stage30.stage30_5_manifest import (
    STAGE30_5_1_ALLOWED_PHX2_IMPORTS,
    STAGE30_5_1_ALLOWED_STDLIB_IMPORTS,
    STAGE30_5_1_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_1,
    STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES,
    STAGE30_5_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_5_MANIFEST_BASENAME,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scanned_sources() -> Dict[str, str]:
    files: Dict[str, str] = {}
    for basename in STAGE30_5_1_SCANNED_PRODUCTION_BASENAMES:
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
    for basename in STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_1:
        path = STAGE30_ROOT / basename
        assert path.is_file(), f"Stage 30.5.1 requires {path}"


def test_scanned_production_basenames_are_the_three_modules() -> None:
    assert STAGE30_5_1_SCANNED_PRODUCTION_BASENAMES == (
        "stage30_5_migration_context_models.py",
        "stage30_5_migration_context_source_protocol.py",
        "stage30_5_migration_context_adapter.py",
    )
    # The manifest is in the production inventory but is not scanned
    # for runtime imports / needles (it is constants-only).
    assert (
        STAGE30_5_MANIFEST_BASENAME
        in STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_1
    )
    assert (
        STAGE30_5_MANIFEST_BASENAME
        not in STAGE30_5_1_SCANNED_PRODUCTION_BASENAMES
    )


def test_every_production_module_imports_cleanly() -> None:
    import PHX2.stage30.stage30_5_migration_context_adapter  # noqa: F401
    import PHX2.stage30.stage30_5_migration_context_models  # noqa: F401
    import PHX2.stage30.stage30_5_migration_context_source_protocol  # noqa: F401,E501
    import PHX2.stage30.stage30_5_manifest  # noqa: F401


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
                module in STAGE30_5_1_ALLOWED_STDLIB_IMPORTS
                or top in STAGE30_5_1_ALLOWED_STDLIB_IMPORTS
            ), (
                f"Stage 30.5.1 module {filename!r} imports non-allowlisted "
                f"stdlib/3rd-party module {module!r}"
            )


def test_phx2_imports_subset_of_allowlist() -> None:
    for filename, text in _scanned_sources().items():
        for module in _imports_of(text):
            if not module.startswith("PHX2."):
                continue
            assert module in STAGE30_5_1_ALLOWED_PHX2_IMPORTS, (
                f"Stage 30.5.1 module {filename!r} imports non-allowlisted "
                f"PHX2 module {module!r}"
            )


# ---------------------------------------------------------------------------
# 3. No os import / no os.environ access
# ---------------------------------------------------------------------------


def test_no_os_import() -> None:
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        assert "os" not in imports, (
            f"Stage 30.5.1 module {filename!r} imports os"
        )
        for module in imports:
            assert not module.startswith("os."), (
                f"Stage 30.5.1 module {filename!r} imports {module!r}"
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
                        f"Stage 30.5.1 module {filename!r} performs "
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
                    f"Stage 30.5.1 module {filename!r} imports network / "
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
                    f"Stage 30.5.1 module {filename!r} imports Stage "
                    f"21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.5.1 module {filename!r} imports PHX1 module "
                f"{module!r}"
            )


def test_no_stage29_5_5_side_channel_import() -> None:
    """Explicitly assert the Stage 29.5.5 private side-channel
    renderer / recorder / artifact writer are never imported
    (Stage 30.5.0 spec lock §6 hard boundary). The forbidden module
    paths are reconstructed at runtime from the manifest so this
    test's own source carries none of the bare needles.
    """
    for filename, text in _scanned_sources().items():
        imports = _imports_of(text)
        for forbidden in STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES:
            assert forbidden not in imports, (
                f"Stage 30.5.1 module {filename!r} imports forbidden "
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
                    f"Stage 30.5.1 module {filename!r} imports provider / "
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
                f"Stage 30.5.1 module {filename!r} carries forbidden "
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
        "compact_body_transport",
        "compact_runtime_session_orchestrator",
    )
    for filename, text in _scanned_sources().items():
        lower = text.lower()
        for needle in needles:
            assert needle.lower() not in lower, (
                f"Stage 30.5.1 module {filename!r} carries transport-"
                f"construction needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. Production module-source guards exposed
# ---------------------------------------------------------------------------


def test_models_exposes_forbidden_field_name_guard() -> None:
    from PHX2.stage30.stage30_5_migration_context_models import (
        FORBIDDEN_RECORD_FIELD_NAMES,
        is_forbidden_record_field_name,
    )

    assert callable(is_forbidden_record_field_name)
    assert len(FORBIDDEN_RECORD_FIELD_NAMES) >= 20
    assert is_forbidden_record_field_name("raw_payload")
    assert is_forbidden_record_field_name("rpc_url")
    assert not is_forbidden_record_field_name("migration_status")


def test_source_protocol_exposes_forbidden_attribute_guard() -> None:
    from PHX2.stage30.stage30_5_migration_context_source_protocol import (  # noqa: E501
        is_source_forbidden_attribute_name,
    )

    assert callable(is_source_forbidden_attribute_name)
    assert is_source_forbidden_attribute_name("api_" + "key")
    assert not is_source_forbidden_attribute_name("read")
