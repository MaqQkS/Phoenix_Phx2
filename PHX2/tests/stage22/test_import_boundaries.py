"""Stage 22 import boundary tests.

Mirrors the Stage 21 ``test_import_boundaries.py`` shape with
the Stage 22 specifics:

  * No import of ``phoenix1`` or any submodule.
  * No import of ``PHX2.stage17``, ``PHX2.stage18``,
    ``PHX2.stage19``, ``PHX2.stage20``.
  * No import of ``PHX2.db`` / ``PHX2.repositories`` /
    ``PHX2.config`` / ``PHX2.models`` / ``PHX2.services`` /
    ``PHX2.dispatch`` / ``PHX2.filters`` / ``PHX2.integrations``
    / ``PHX2.renderers`` / ``PHX2.scripts`` / ``PHX2.analysis``.
  * No top-level import of a network / messaging / scheduler /
    DB / secrets library (substring match against lowered import
    name).
  * No import of the Stage 21 fake-path modules
    (``fake_provider``, ``fake_transport``,
    ``live_path_simulator``), the Stage 21.3B Helius adapter,
    the Stage 21.3C Discord transport, the Stage 21.4 private
    smoke runner, the Stage 21 env-read seam (``config``), or
    the Stage 21.3A live-readiness boundary.
  * Allowed Stage 21 imports are limited to
    ``PHX2.stage21.normalized_events`` and (optionally) the
    safe-content predicate. Stage 22.1 does NOT need
    ``PHX2.stage21.clock``, ``PHX2.stage21.transport_contracts``,
    or ``PHX2.stage21.constants`` at runtime.

The checks run AST-level on Stage 22 production .py files only
(``PHX2/stage22/**``). Test files under ``PHX2/tests/stage22/``
are deliberately exempt -- tests may import Stage 21 constants
to compare forbidden-token tuples.
"""

from __future__ import annotations

import ast
from pathlib import Path


STAGE22_ROOT = Path(__file__).parent.parent.parent / "stage22"


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
)


_FORBIDDEN_PHX2_RUNTIME_PREFIXES: tuple[str, ...] = (
    "PHX2.db",
    "PHX2.repositories",
    "PHX2.config",
    "PHX2.models",
    "PHX2.services",
    "PHX2.dispatch",
    "PHX2.filters",
    "PHX2.integrations",
    "PHX2.renderers",
    "PHX2.scripts",
    "PHX2.analysis",
)


# Forbidden Stage 21 neighbour modules. Stage 22.1 production
# code does NOT import any of these. Stage 22.5 lifts the
# forbidden status for a specific allowlisted subset on
# ``live_composition.py`` ONLY -- see
# ``_LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES`` below. Every other
# Stage 22 production module remains forbidden from importing any
# entry in this tuple.
#
#   * fake_provider / fake_transport / live_path_simulator:
#     the Stage 21.2 fake-path boundary.
#   * provider_adapter_helius: live composition wraps this; every
#     other Stage 22 file is forbidden.
#   * discord_private_transport: live composition wraps this;
#     every other Stage 22 file is forbidden.
#   * private_smoke_runner: the Stage 21.4 single-shot runner;
#     Stage 22.5 ships its own bounded runner.
#   * config: the Stage 21 env-read seam. Stage 22 has no
#     env-reading module.
#   * live_secrets_boundary: the Stage 21.3A readiness gate.
#     Live composition uses the offline helpers
#     (``load_live_readiness_config_from_env`` / ``evaluate_live_readiness``);
#     every other Stage 22 file is forbidden.
_FORBIDDEN_STAGE21_NEIGHBOUR_MODULES: tuple[str, ...] = (
    "PHX2.stage21.fake_provider",
    "PHX2.stage21.fake_transport",
    "PHX2.stage21.live_path_simulator",
    "PHX2.stage21.provider_adapter_helius",
    "PHX2.stage21.discord_private_transport",
    "PHX2.stage21.private_smoke_runner",
    "PHX2.stage21.config",
    "PHX2.stage21.live_secrets_boundary",
)


# Stage 22.5 live composition allowlist. ``live_composition.py``
# is the SINGLE Stage 22 production seam permitted to import
# from the Stage 21 live-path family. The set is locked: any
# addition requires a Stage 22.5+ design decision plus a paired
# test update. The bounded private ingest runner
# (``bounded_live_runner.py``) imports NOTHING from Stage 21;
# the runner's Stage 21 dependency surface fans through
# ``live_composition.py`` only.
_LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES: frozenset[str] = frozenset({
    "PHX2.stage21.live_secrets_boundary",
    "PHX2.stage21.provider_adapter_helius",
    "PHX2.stage21.provider_event_decoder",
    "PHX2.stage21.discord_private_transport",
    "PHX2.stage21.transport_contracts",
    "PHX2.stage21.allowlist",
    "PHX2.stage21.secret_redaction",
})


_LIVE_COMPOSITION_FILE_NAME: str = "live_composition.py"


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    # Network / RPC
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    # Provider clients
    "helius",
    "birdeye",
    "dexscreener",
    "jupiter",
    "jito",
    # Messaging
    "discord",
    "telegram",
    "telethon",
    "webhook",
    # Scheduler / daemon
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "daemon",
    # DB
    "sqlalchemy",
    "sqlite3",
    # Secrets-management libs
    "dotenv",
    "keyring",
)


_DYNAMIC_IMPORT_FUNC_NAMES: frozenset[str] = frozenset({
    "import_module",
    "__import__",
})


def _iter_production_modules() -> list[Path]:
    return [
        p for p in STAGE22_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _collect_import_targets_from_source(
    source: str,
) -> tuple[set[str], set[str]]:
    """Return ``(modules, full_targets)`` for ``source``.

    Mirrors the Stage 21 collector exactly (same AST shapes,
    same dynamic-import-call detection, same aliasing).
    """
    tree = ast.parse(source)
    modules: set[str] = set()
    full_targets: set[str] = set()

    dynamic_import_aliases: set[str] = set(_DYNAMIC_IMPORT_FUNC_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name in _DYNAMIC_IMPORT_FUNC_NAMES:
                    bound_name = alias.asname or alias.name
                    dynamic_import_aliases.add(bound_name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                full_targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
                full_targets.add(mod)
            for alias in node.names:
                if mod:
                    full_targets.add(f"{mod}.{alias.name}")
        elif isinstance(node, ast.Call):
            func = node.func
            is_dynamic_import = False
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "import_module"
            ):
                is_dynamic_import = True
            elif (
                isinstance(func, ast.Name)
                and func.id in dynamic_import_aliases
            ):
                is_dynamic_import = True
            if is_dynamic_import and node.args:
                first = node.args[0]
                if (
                    isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                ):
                    modules.add(first.value)
                    full_targets.add(first.value)

    return modules, full_targets


def _collect_modules(file_path: Path) -> set[str]:
    modules, _ = _collect_import_targets_from_source(
        file_path.read_text(encoding="utf-8")
    )
    return modules


def _collect_full_targets(file_path: Path) -> set[str]:
    _, full = _collect_import_targets_from_source(
        file_path.read_text(encoding="utf-8")
    )
    return full


# ---------------------------------------------------------------------------
# Production-tree checks
# ---------------------------------------------------------------------------


def test_at_least_one_production_module_exists():
    files = _iter_production_modules()
    assert files, "expected at least one production .py under stage22"


def test_no_phoenix1_imports():
    for py_file in _iter_production_modules():
        for target in _collect_full_targets(py_file):
            assert not target.startswith("phoenix1"), (
                f"{py_file}: forbidden phoenix1 import target {target!r}"
            )


def test_no_prior_stage_runtime_imports():
    for py_file in _iter_production_modules():
        for target in _collect_full_targets(py_file):
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{py_file}: forbidden prior-stage target {target!r}"
                )


def test_no_phx2_runtime_layer_imports():
    for py_file in _iter_production_modules():
        for target in _collect_full_targets(py_file):
            for forbidden in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{py_file}: forbidden PHX2 runtime-layer target "
                    f"{target!r}"
                )


def test_no_forbidden_stage21_neighbour_imports():
    for py_file in _iter_production_modules():
        is_live_composition = py_file.name == _LIVE_COMPOSITION_FILE_NAME
        modules = _collect_modules(py_file)
        for module in modules:
            for forbidden in _FORBIDDEN_STAGE21_NEIGHBOUR_MODULES:
                if (
                    is_live_composition
                    and module in _LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES
                ):
                    continue
                assert module != forbidden, (
                    f"{py_file}: forbidden Stage 21 neighbour import "
                    f"{module!r}"
                )


def test_no_forbidden_runtime_module_patterns():
    # Module-paths only -- identifier names imported FROM a Stage 22
    # module must not be substring-checked against runtime library
    # patterns. ``live_composition.py`` is allowed to import a
    # locked subset of Stage 21 modules whose names contain the
    # ``helius`` / ``discord`` substrings; those imports are
    # exempt from the substring scan because the underlying
    # modules are Stage 21 boundaries, not external runtime
    # libraries.
    for py_file in _iter_production_modules():
        is_live_composition = py_file.name == _LIVE_COMPOSITION_FILE_NAME
        for module in _collect_modules(py_file):
            if (
                is_live_composition
                and module in _LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES
            ):
                continue
            lower = module.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{py_file}: forbidden module pattern {pattern!r} "
                    f"in import target {module!r}"
                )


def test_no_bot_db_reference_anywhere_in_stage22_source():
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        assert "bot.db" not in source, (
            f"{py_file}: forbidden 'bot.db' reference in source"
        )


# ---------------------------------------------------------------------------
# Stage 22-specific allowed-import discipline
# ---------------------------------------------------------------------------


def test_stage22_production_only_imports_safe_stage21_modules():
    """Stage 22 production code may import from PHX2.stage21 ONLY:

      * ``PHX2.stage21.normalized_events`` -- for ``NormalizedLiveEvent``.
      * ``PHX2.stage21.safe_content``      -- optional safe-content
                                              predicate helpers.

    Stage 22.5 lifts this restriction for ONE file:
    ``live_composition.py`` may additionally import the locked
    subset in ``_LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES``.
    Every other ``PHX2.stage21.*`` import is forbidden in Stage
    22 production code.
    """
    allowed_stage21_prefixes: tuple[str, ...] = (
        "PHX2.stage21.normalized_events",
        "PHX2.stage21.safe_content",
    )
    for py_file in _iter_production_modules():
        is_live_composition = py_file.name == _LIVE_COMPOSITION_FILE_NAME
        modules = _collect_modules(py_file)
        for module in modules:
            if not module.startswith("PHX2.stage21"):
                continue
            allowed_by_prefix = any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in allowed_stage21_prefixes
            )
            allowed_by_live_composition = (
                is_live_composition
                and module in _LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES
            )
            assert allowed_by_prefix or allowed_by_live_composition, (
                f"{py_file}: disallowed Stage 21 import {module!r}; "
                "Stage 22 production code may only import "
                "PHX2.stage21.normalized_events or "
                "PHX2.stage21.safe_content (plus the live_composition "
                "allowlist for that one file)"
            )


def test_live_composition_is_only_stage22_file_importing_locked_stage21_modules():
    """Stage 22.5 invariant: the live composition seam
    (``live_composition.py``) is the SINGLE Stage 22 production
    file that imports any module in
    ``_LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES``. Every other
    Stage 22 production module must avoid the entire allowlisted
    set so the Stage 21 dependency surface fans through one seam.
    """
    for py_file in _iter_production_modules():
        if py_file.name == _LIVE_COMPOSITION_FILE_NAME:
            continue
        modules = _collect_modules(py_file)
        leaked = sorted(
            modules & _LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES
        )
        assert not leaked, (
            f"{py_file}: Stage 22 production module imports "
            f"live-composition-only Stage 21 modules {leaked!r}; the "
            f"Stage 22 production tree must fan its Stage 21 "
            f"dependency surface through live_composition.py only"
        )


# ---------------------------------------------------------------------------
# Negative fixtures: prove the collector flags every problem shape
# ---------------------------------------------------------------------------


def _has_forbidden_prior_stage(source: str) -> bool:
    _, full_targets = _collect_import_targets_from_source(source)
    for target in full_targets:
        for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
            if target.startswith(forbidden):
                return True
    return False


def test_collector_catches_dotted_from_import_with_member():
    source = "from PHX2.stage20.constants import STAGE20_VERSION\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_from_phx2_import_stage20():
    source = "from PHX2 import stage20\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_import_dotted_phx2_stage20():
    source = "import PHX2.stage20\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_importlib_import_module_literal():
    source = (
        "import importlib\n"
        "m = importlib.import_module('PHX2.stage20.constants')\n"
    )
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_bare_import_module_literal():
    source = (
        "from importlib import import_module\n"
        "m = import_module('PHX2.stage20')\n"
    )
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_dunder_import_literal():
    source = "__import__('PHX2.stage20.constants')\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_does_not_catch_docstring_mention():
    source = '"""Docstring mentions PHX2.stage20 but does not import it."""\n'
    assert not _has_forbidden_prior_stage(source)


def test_collector_does_not_catch_string_literal_mention():
    source = "_REFERENCE = 'PHX2.stage20.constants'\n"
    assert not _has_forbidden_prior_stage(source)


def test_collector_catches_aliased_importlib():
    source = (
        "from importlib import import_module as _im\n"
        "m = _im('PHX2.stage20')\n"
    )
    assert _has_forbidden_prior_stage(source)


def test_collector_recognizes_stage21_neighbour_targets():
    source = "from PHX2.stage21 import fake_provider\n"
    modules, full_targets = _collect_import_targets_from_source(source)
    assert "PHX2.stage21.fake_provider" in full_targets
    assert "PHX2.stage21" in modules


def test_collector_catches_db_via_from_phx2_import_db():
    source = "from PHX2 import db\n"
    _, full_targets = _collect_import_targets_from_source(source)
    assert "PHX2.db" in full_targets
