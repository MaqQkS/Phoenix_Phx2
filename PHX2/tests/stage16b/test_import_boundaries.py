"""Stage 16B import boundary checks: AST forward/reverse direction plus a runtime transitive-import check.

Forward direction (every .py file under ``PHX2/stage16b/`` plus
``PHX2/scripts/run_stage16b_observer_once.py``) MUST NOT import any
module that would couple Stage 16B to the alert flow or to a
secret/config-loading surface:

  * network libraries (requests, httpx, aiohttp, urllib3, socket)
  * asyncio
  * PHX2.config (transitively pulls in PHX2.models.enums)
  * PHX2.services / PHX2.filters / PHX2.dispatch / PHX2.renderers /
    PHX2.integrations
  * PHX2.models (Stage 16B owns its own models surface)
  * any prior pipeline stage (PHX2.stage0 .. PHX2.stage15)
  * PHX2.db.connection (transitively loads PHX2.config.settings)
  * PHX2.db.repositories (transitively loads PHX2.models)

Stage 16B MAY import:

  * stdlib (any)
  * PHX2.stage16a.*
  * PHX2.db.migrations (provisioning surface; PHX2.db.migrations' own
    transitive PHX2.config.settings load is deferred into
    ``migrate_phx2_schema`` so simply importing it is clean)

Reverse direction:

  * Stage 16A MUST NOT import Stage 16B (would re-introduce the live
    decision path coupling Stage 16B's sidecar architecture is designed
    to avoid).
  * Alert-flow modules under PHX2/services, PHX2/filters, PHX2/dispatch,
    PHX2/renderers, PHX2/integrations MUST NOT import Stage 16B.

Runtime check: ``test_runtime_imports_do_not_load_forbidden_modules``
spawns a fresh Python interpreter, imports every Stage 16B runtime-path
module (CLI, observer, repository, assembler, row_builder, models,
errors, script entry), and asserts that ``sys.modules`` does NOT
contain any of the forbidden transitive surfaces (``PHX2.config*``,
``PHX2.models*``, ``PHX2.services``, ``PHX2.filters``, ``PHX2.dispatch``,
``PHX2.renderers``, ``PHX2.integrations``).

These boundary checks are AST + runtime. Predicate-field grep checks
would be brittle and the matching-logic reuse invariant is already
proven by Phase 6's behavior tests
(``test_observer_uses_stage16a_evaluator.py``).
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


# This file lives at PHX2/tests/stage16b/test_import_boundaries.py
# so ``parents[3]`` is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE16A_DIR = REPO_ROOT / "PHX2" / "stage16a"
STAGE16B_DIR = REPO_ROOT / "PHX2" / "stage16b"
STAGE16B_SCRIPT = REPO_ROOT / "PHX2" / "scripts" / "run_stage16b_observer_once.py"


# ---------------------------------------------------------------------------
# Forbidden-import policy for Stage 16B production code
# ---------------------------------------------------------------------------


FORBIDDEN_EXACT: frozenset[str] = frozenset({
    "asyncio",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "socket",
    # Legacy alias kept here for parity with Stage 16A's boundary policy.
    "PHX2.database",
})


FORBIDDEN_PREFIXES: tuple[str, ...] = (
    # PHX2.config: transitively imports PHX2.models.enums, which Stage 16B
    # owns its own equivalents for. Also the canonical secrets surface.
    "PHX2.config",
    # Alert-flow surfaces.
    "PHX2.services",
    "PHX2.filters",
    "PHX2.dispatch",
    "PHX2.renderers",
    "PHX2.integrations",
    # PHX2.models: Stage 16B has its own minimal model module.
    "PHX2.models",
    # Prior pipeline stages -- stage16a/b are carved out below in
    # ``_is_allowed_stage_carveout``.
    "PHX2.stage0",
    "PHX2.stage1",
    "PHX2.stage2",
    "PHX2.stage3",
    "PHX2.stage4",
    "PHX2.stage5",
    "PHX2.stage6",
    "PHX2.stage7",
    "PHX2.stage8",
    "PHX2.stage9",
    "PHX2.stage10",
    "PHX2.stage11",
    "PHX2.stage12",
    "PHX2.stage13",
    "PHX2.stage14",
    "PHX2.stage15",
)


# Stage carve-outs: stage16a and stage16b match the ``PHX2.stage``
# prefix conceptually but are explicitly allowed.
ALLOWED_STAGE_CARVEOUTS: tuple[str, ...] = (
    "PHX2.stage16a",
    "PHX2.stage16b",
)


# PHX2.db submodules Stage 16B may import. The audit narrowed this list:
# PHX2.db.connection and PHX2.db.repositories both transitively load
# forbidden PHX2.config / PHX2.models surfaces and MUST NOT appear in
# Stage 16B production imports.
ALLOWED_PHX2_DB_SUBMODULES: frozenset[str] = frozenset({
    "PHX2.db.migrations",
})


# ---------------------------------------------------------------------------
# AST collection
# ---------------------------------------------------------------------------


def _collect_imports_with_names(py_file: Path) -> list[tuple[str, set[str]]]:
    """Walk the AST of ``py_file`` and yield ``(dotted_module, imported_names)``.

    ``import X``               -> ("X", {"X"})
    ``import X.Y``             -> ("X.Y", {"X.Y"})
    ``from X import Y``        -> ("X", {"Y"})
    ``from X import Y, Z``     -> ("X", {"Y", "Z"})
    ``from . import X``        -> ignored (relative, always Stage 16B-local)
    """

    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    results: list[tuple[str, set[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((alias.name, {alias.name}))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import -- always Stage 16B-local; ignore.
                continue
            if node.module:
                names = {alias.name for alias in node.names}
                results.append((node.module, names))
    return results


def _collect_module_names(py_file: Path) -> set[str]:
    """Return just the dotted module names imported by ``py_file``.

    Convenience for the reverse-direction checks that don't need the
    per-import names tuple.
    """

    return {module for module, _ in _collect_imports_with_names(py_file)}


# ---------------------------------------------------------------------------
# Forward policy
# ---------------------------------------------------------------------------


def _is_allowed_stage_carveout(module: str) -> bool:
    return any(
        module == p or module.startswith(p + ".") for p in ALLOWED_STAGE_CARVEOUTS
    )


def _is_forbidden(
    module: str,
    imported_names: set[str],
) -> tuple[bool, str]:
    """Return ``(forbidden, reason)``.

    Carve-out order:
      1. PHX2.stage16a.* / PHX2.stage16b.* are allowed.
      2. PHX2.db.connection / PHX2.db.migrations are allowed.
      3. PHX2.db.repositories is allowed only for RepositoryContract.
      4. Bare PHX2.db or other PHX2.db.* submodules are denied.
      5. FORBIDDEN_EXACT and FORBIDDEN_PREFIXES rules apply.
    """

    if _is_allowed_stage_carveout(module):
        return False, ""

    if module == "PHX2.db":
        return (
            True,
            "bare PHX2.db import would re-export alert-flow concrete repositories",
        )

    if module == "PHX2.db.connection":
        return (
            True,
            "PHX2.db.connection transitively loads PHX2.config.settings and "
            "PHX2.models.enums (audit HIGH finding)",
        )

    if module == "PHX2.db.repositories":
        return (
            True,
            "PHX2.db.repositories transitively loads PHX2.models barrel "
            "(audit HIGH finding); Stage 16B uses raw sqlite3 instead",
        )

    if module in ALLOWED_PHX2_DB_SUBMODULES:
        return False, ""

    if module.startswith("PHX2.db."):
        return True, f"unrecognized PHX2.db submodule: {module}"

    if module in FORBIDDEN_EXACT:
        return True, f"exact-match forbidden: {module}"

    for prefix in FORBIDDEN_PREFIXES:
        if module == prefix or module.startswith(prefix + "."):
            return True, f"forbidden prefix: {module} starts with {prefix}"

    return False, ""


# ---------------------------------------------------------------------------
# Forward direction: PHX2/stage16b/ has no forbidden imports
# ---------------------------------------------------------------------------


def _stage16b_production_files() -> list[Path]:
    files = sorted(STAGE16B_DIR.rglob("*.py"))
    if STAGE16B_SCRIPT.exists():
        files.append(STAGE16B_SCRIPT)
    return files


def test_stage16b_production_files_exist() -> None:
    assert _stage16b_production_files(), (
        f"no Python files found under {STAGE16B_DIR}"
    )


def test_stage16b_has_no_forbidden_imports() -> None:
    violations: list[tuple[str, str, str]] = []
    for py in _stage16b_production_files():
        for module, names in _collect_imports_with_names(py):
            forbidden, reason = _is_forbidden(module, names)
            if forbidden:
                rel = py.relative_to(REPO_ROOT)
                violations.append((str(rel), module, reason))

    assert not violations, (
        "Stage 16B production modules import forbidden symbols:\n  "
        + "\n  ".join(
            f"{f}: {imp}  ({why})" for f, imp, why in violations
        )
    )


@pytest.mark.parametrize("py_file", _stage16b_production_files())
def test_per_file_no_forbidden_imports(py_file: Path) -> None:
    """Per-file variant of the aggregate boundary check; pytest reports
    each offending file separately."""

    file_violations: list[tuple[str, str]] = []
    for module, names in _collect_imports_with_names(py_file):
        forbidden, reason = _is_forbidden(module, names)
        if forbidden:
            file_violations.append((module, reason))
    assert not file_violations, (
        f"{py_file.relative_to(REPO_ROOT)} imports forbidden symbols: "
        f"{file_violations!r}"
    )


def test_stage16b_repository_does_not_import_phx2_db_repositories() -> None:
    """Audit-required: ``PHX2/stage16b/repository.py`` MUST NOT import
    anything from ``PHX2.db.repositories``. Importing that module
    transitively loads ``PHX2.models`` barrel (HIGH finding); Stage
    16B's repository is a top-level class on raw ``sqlite3.Connection``
    instead.
    """

    target = STAGE16B_DIR / "repository.py"
    for module, _names in _collect_imports_with_names(target):
        assert module != "PHX2.db.repositories", (
            f"{target.relative_to(REPO_ROOT)} imports PHX2.db.repositories"
        )
        assert not module.startswith("PHX2.db.repositories."), (
            f"{target.relative_to(REPO_ROOT)} imports PHX2.db.repositories.*"
        )


def test_stage16b_cli_does_not_import_phx2_db_connection() -> None:
    """Audit-required: ``PHX2/stage16b/cli.py`` MUST NOT import
    ``PHX2.db.connection``. That module transitively loads
    ``PHX2.config.settings`` and ``PHX2.models.enums`` (HIGH finding);
    Stage 16B's CLI opens a raw ``sqlite3.Connection`` directly.
    """

    target = STAGE16B_DIR / "cli.py"
    for module, _names in _collect_imports_with_names(target):
        assert module != "PHX2.db.connection", (
            f"{target.relative_to(REPO_ROOT)} imports PHX2.db.connection"
        )
        assert not module.startswith("PHX2.db.connection."), (
            f"{target.relative_to(REPO_ROOT)} imports PHX2.db.connection.*"
        )


def test_stage16b_does_not_import_phx2_config() -> None:
    """PHX2.config transitively pulls in PHX2.models.enums; Stage 16B
    constructs PHX2Connection directly to avoid this transitivity."""

    violations: list[tuple[str, str]] = []
    for py in _stage16b_production_files():
        for module, _names in _collect_imports_with_names(py):
            if module == "PHX2.config" or module.startswith("PHX2.config."):
                rel = py.relative_to(REPO_ROOT)
                violations.append((str(rel), module))
    assert not violations, (
        f"Stage 16B imports PHX2.config (transitively pulls models/enums): "
        f"{violations!r}"
    )


# ---------------------------------------------------------------------------
# Reverse direction: nobody else imports Stage 16B
# ---------------------------------------------------------------------------


def _imports_stage16b(module: str) -> bool:
    return module == "PHX2.stage16b" or module.startswith("PHX2.stage16b.")


def test_stage16a_does_not_import_stage16b() -> None:
    """Stage 16A is upstream of Stage 16B; the reverse import would
    re-introduce the runtime coupling Stage 16A's import-boundary tests
    already forbid for the broader PHX2 surface."""

    violations: list[tuple[str, str]] = []
    for py in sorted(STAGE16A_DIR.rglob("*.py")):
        for module in _collect_module_names(py):
            if _imports_stage16b(module):
                rel = py.relative_to(REPO_ROOT)
                violations.append((str(rel), module))
    assert not violations, (
        f"Stage 16A modules import Stage 16B: {violations!r}"
    )


REVERSE_SCAN_DIRS = (
    REPO_ROOT / "PHX2" / "services",
    REPO_ROOT / "PHX2" / "filters",
    REPO_ROOT / "PHX2" / "dispatch",
    REPO_ROOT / "PHX2" / "renderers",
    REPO_ROOT / "PHX2" / "integrations",
)


def test_alert_flow_modules_do_not_import_stage16b() -> None:
    """Every .py file under PHX2/services, PHX2/filters, PHX2/dispatch,
    PHX2/renderers, PHX2/integrations MUST NOT import Stage 16B.

    This is the structural lock that guarantees no live decision path can
    call into Stage 16B and inherit its observe-only telemetry as a
    blocking signal."""

    violations: list[tuple[str, str]] = []
    for scan_dir in REVERSE_SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for py in scan_dir.rglob("*.py"):
            for module in _collect_module_names(py):
                if _imports_stage16b(module):
                    rel = py.relative_to(REPO_ROOT)
                    violations.append((str(rel), module))
    assert not violations, (
        "Alert-flow modules import Stage 16B (this would break sidecar "
        f"isolation):\n  " + "\n  ".join(f"{f}: {imp}" for f, imp in violations)
    )


def test_alert_eligibility_engine_does_not_import_stage16b() -> None:
    target = REPO_ROOT / "PHX2" / "services" / "alert_eligibility_engine.py"
    if not target.exists():
        pytest.skip(f"{target} not found")
    for module in _collect_module_names(target):
        assert not _imports_stage16b(module), (
            f"alert_eligibility_engine imports Stage 16B: {module!r}"
        )


def test_filter_evaluation_engine_does_not_import_stage16b() -> None:
    target = REPO_ROOT / "PHX2" / "services" / "filter_evaluation_engine.py"
    if not target.exists():
        pytest.skip(f"{target} not found")
    for module in _collect_module_names(target):
        assert not _imports_stage16b(module), (
            f"filter_evaluation_engine imports Stage 16B: {module!r}"
        )


def test_stage16b_tests_dir_unconstrained() -> None:
    """Documentation test: the boundary policy applies to
    ``PHX2/stage16b/`` production code only. The Stage 16B test
    directory may import test-only helpers (analysis_fixture_builder
    etc.). This test exists to pin that distinction."""

    tests_dir = REPO_ROOT / "PHX2" / "tests" / "stage16b"
    assert tests_dir.is_dir()
    # No assertion on contents; this test exists to document the carve-out.


# ---------------------------------------------------------------------------
# Runtime transitive-import test (audit HIGH-finding fix)
# ---------------------------------------------------------------------------
#
# The forward-direction AST scan above only catches direct imports of
# forbidden modules. It cannot catch transitive imports: e.g., a Stage
# 16B module imports ``PHX2.db.connection`` (allowed by AST scan),
# which itself imports ``PHX2.config.settings`` (forbidden). The audit
# flagged this transitive leak as a HIGH finding.
#
# The runtime test below spawns a fresh Python interpreter, imports
# every Stage 16B runtime-path module, and asserts that none of the
# forbidden surfaces ended up in ``sys.modules``. It runs as a
# subprocess so the parent pytest session's module cache cannot pollute
# the check.


_RUNTIME_FORBIDDEN_MODULES: tuple[str, ...] = (
    "PHX2.config",
    "PHX2.config.settings",
    "PHX2.models",
    "PHX2.models.enums",
    "PHX2.services",
    "PHX2.filters",
    "PHX2.dispatch",
    "PHX2.renderers",
    "PHX2.integrations",
    "PHX2.db.connection",
    "PHX2.db.repositories",
)


_RUNTIME_IMPORT_PROBE = textwrap.dedent(
    """
    import sys

    # Audit re-finding: PHX2.stage16b.migrations was previously excluded
    # from this probe because it is "provisioning-only" -- and the
    # exclusion silently masked a HIGH leak through
    # ``PHX2/db/__init__.py`` (eager imports of PHX2.db.connection +
    # PHX2.db.repositories). The probe now imports the full Stage 16B
    # surface, including migrations, and asserts NO forbidden modules
    # are loaded transitively.
    import PHX2.stage16b
    import PHX2.stage16b.errors
    import PHX2.stage16b.models
    import PHX2.stage16b.row_builder
    import PHX2.stage16b.decision_context_assembler
    import PHX2.stage16b.repository
    import PHX2.stage16b.observer
    import PHX2.stage16b.cli
    import PHX2.stage16b.migrations
    import PHX2.scripts.run_stage16b_observer_once

    forbidden = {forbidden!r}
    leaked = sorted(m for m in forbidden if m in sys.modules)
    if leaked:
        sys.stdout.write("LEAKED " + repr(leaked))
        sys.exit(2)
    sys.stdout.write("CLEAN")
    """
)


def test_runtime_imports_do_not_load_forbidden_modules() -> None:
    """Spawn a fresh Python interpreter, import the Stage 16B runtime
    surface, and assert no forbidden modules are loaded transitively.

    This is the runtime sibling of the AST forward-direction check. It
    catches the case the audit flagged as HIGH: a Stage 16B module
    imports something AST-allowed (e.g., ``PHX2.db.migrations``) which
    in turn imports a forbidden module (e.g., ``PHX2.config.settings``).

    The probe is run in a subprocess so the parent pytest session's
    pre-loaded modules cannot mask a real leak.
    """

    probe = _RUNTIME_IMPORT_PROBE.format(forbidden=_RUNTIME_FORBIDDEN_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Runtime import probe failed.\n"
        f"  stdout: {result.stdout!r}\n"
        f"  stderr: {result.stderr!r}"
    )
    assert result.stdout.strip() == "CLEAN", (
        f"Stage 16B runtime imports transitively loaded forbidden modules: "
        f"{result.stdout!r}"
    )


def test_runtime_import_of_stage16b_migrations_alone_is_clean() -> None:
    """Audit re-finding HIGH regression: ``python -c "import
    PHX2.stage16b.migrations"`` must NOT load any forbidden module.

    This isolates the specific path Codex flagged: previously,
    ``import PHX2.stage16b.migrations`` triggered
    ``PHX2/db/__init__.py`` to execute, which eagerly imported
    ``PHX2.db.connection`` and ``PHX2.db.repositories`` and
    transitively loaded ``PHX2.config.settings`` and ``PHX2.models``.
    The fix moves the barrel imports under PEP 562 ``__getattr__`` so
    they are only loaded on first attribute access.
    """

    probe = textwrap.dedent(
        """
        import sys
        import PHX2.stage16b.migrations
        forbidden = {forbidden!r}
        leaked = sorted(m for m in forbidden if m in sys.modules)
        if leaked:
            sys.stdout.write("LEAKED " + repr(leaked))
            sys.exit(2)
        sys.stdout.write("CLEAN")
        """
    ).format(forbidden=_RUNTIME_FORBIDDEN_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"importing PHX2.stage16b.migrations leaks forbidden modules: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "CLEAN"


@pytest.mark.parametrize(
    "module_name",
    [
        "PHX2.stage16b",
        "PHX2.stage16b.errors",
        "PHX2.stage16b.models",
        "PHX2.stage16b.row_builder",
        "PHX2.stage16b.decision_context_assembler",
        "PHX2.stage16b.repository",
        "PHX2.stage16b.observer",
        "PHX2.stage16b.cli",
        "PHX2.stage16b.migrations",
        "PHX2.scripts.run_stage16b_observer_once",
    ],
)
def test_runtime_import_of_single_stage16b_module_is_clean(
    module_name: str,
) -> None:
    """Per-module probe: importing each Stage 16B surface module in a
    fresh interpreter must not leak any forbidden module. Catches
    drift in any individual module's transitive import chain."""

    probe = textwrap.dedent(
        """
        import sys
        import {module}
        forbidden = {forbidden!r}
        leaked = sorted(m for m in forbidden if m in sys.modules)
        if leaked:
            sys.stdout.write("LEAKED " + repr(leaked))
            sys.exit(2)
        sys.stdout.write("CLEAN")
        """
    ).format(module=module_name, forbidden=_RUNTIME_FORBIDDEN_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"importing {module_name!r} alone leaks forbidden modules: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "CLEAN"


def test_runtime_imports_probe_detects_forbidden_module_smoke() -> None:
    """Self-check: the probe machinery actually detects a leak when one
    exists. We re-run the probe but inject an ``import PHX2.config.settings``
    (a known forbidden surface) and confirm the probe surfaces it.

    This pins the probe's negative case so a future change that
    silently downgrades it (e.g., always-succeed) is caught.
    """

    leaky_probe = (
        _RUNTIME_IMPORT_PROBE.replace(
            "import PHX2.stage16b",
            "import PHX2.config.settings  # noqa\nimport PHX2.stage16b",
            1,
        )
    ).format(forbidden=_RUNTIME_FORBIDDEN_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", leaky_probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, (
        f"Leaky probe should have exited 2; got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "LEAKED" in result.stdout, (
        f"Leaky probe should have surfaced LEAKED output: {result.stdout!r}"
    )
    assert "PHX2.config.settings" in result.stdout
