"""Stage 17 import-boundary checks.

The locked policy (verbatim from the Stage 17 contract): every file
under ``PHX2/stage17/`` MUST NOT import from any of these prefixes:

  * PHX2.services
  * PHX2.dispatch
  * PHX2.integrations
  * PHX2.filters
  * PHX2.stage16a (Stage 17 reads the persisted table, not the
    runtime policy object)
  * PHX2.stage16b (same reason)
  * PHX2.db.repositories
  * PHX2.db.connection
  * PHX2.config
  * PHX2.models
  * PHX2.analysis (Stage 12's WINDOWS constant is deliberately
    duplicated locally in PHX2/stage17/windows.py)
  * any third-party package not in the standard library

Verified two ways:

  1. Static AST check: walk every ``*.py`` under ``PHX2/stage17/``,
     parse imports, and assert no statement targets a forbidden
     module.
  2. Runtime check: spawn a fresh Python interpreter, import each
     Stage 17 surface module, and assert no forbidden module ended
     up in ``sys.modules`` transitively.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE17_DIR = REPO_ROOT / "PHX2" / "stage17"
STAGE17_SCRIPT = REPO_ROOT / "PHX2" / "scripts" / "run_stage17_analysis.py"


# Allowed standard-library modules used by Stage 17 source. Any other
# third-party import is a boundary violation.
ALLOWED_STDLIB_MODULES: frozenset[str] = frozenset({
    "sqlite3", "argparse", "dataclasses", "datetime", "hashlib",
    "json", "pathlib", "csv", "statistics", "typing", "os",
    "subprocess", "sys", "contextlib", "collections", "enum",
    "math", "traceback", "io", "__future__",
})


FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "PHX2.services",
    "PHX2.dispatch",
    "PHX2.integrations",
    "PHX2.filters",
    "PHX2.stage16a",
    "PHX2.stage16b",
    "PHX2.db.repositories",
    "PHX2.db.connection",
    "PHX2.config",
    "PHX2.models",
    "PHX2.analysis",
)


ALLOWED_PHX2_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
)


def _collect_imports(py_file: Path) -> list[str]:
    """Return the list of dotted module names imported by ``py_file``."""

    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import
            if node.module:
                out.append(node.module)
    return out


def _stage17_production_files() -> list[Path]:
    files = sorted(STAGE17_DIR.rglob("*.py"))
    if STAGE17_SCRIPT.exists():
        files.append(STAGE17_SCRIPT)
    return files


def test_stage17_production_files_exist() -> None:
    assert _stage17_production_files(), (
        f"no Python files found under {STAGE17_DIR}"
    )


@pytest.mark.parametrize("py_file", _stage17_production_files())
def test_per_file_has_no_forbidden_phx2_imports(py_file: Path) -> None:
    violations: list[str] = []
    for module in _collect_imports(py_file):
        for prefix in FORBIDDEN_PREFIXES:
            if module == prefix or module.startswith(prefix + "."):
                violations.append(module)
    assert not violations, (
        f"{py_file.relative_to(REPO_ROOT)} imports forbidden modules: "
        f"{violations!r}"
    )


@pytest.mark.parametrize("py_file", _stage17_production_files())
def test_per_file_only_imports_allowed_modules(py_file: Path) -> None:
    """Every imported module must be either stdlib (allowlist) or a
    Stage 17 internal."""

    violations: list[str] = []
    for module in _collect_imports(py_file):
        # Allow Stage 17-internal references.
        if any(
            module == p or module.startswith(p + ".") for p in ALLOWED_PHX2_PREFIXES
        ):
            continue
        # Strip submodule from "json.x" etc. for the stdlib allowlist check.
        top = module.split(".")[0]
        if top in ALLOWED_STDLIB_MODULES:
            continue
        # Anything else is a violation.
        violations.append(module)

    assert not violations, (
        f"{py_file.relative_to(REPO_ROOT)} imports modules outside the "
        f"locked allowlist: {violations!r}"
    )


def test_static_grep_for_forbidden_phx2_prefixes() -> None:
    """Audit-required static check: a regex scan of source must return
    no hits on the forbidden prefixes. Mirrors the audit grep in the
    Stage 17 contract."""

    import re

    pattern = re.compile(
        r"from\s+PHX2\.(services|dispatch|integrations|filters|stage16a|"
        r"stage16b|config|models|analysis|db\.repositories|db\.connection)"
    )
    violations: list[tuple[str, int, str]] = []
    for py in _stage17_production_files():
        for idx, line in enumerate(
            py.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                violations.append(
                    (str(py.relative_to(REPO_ROOT)), idx, line.strip())
                )
    assert not violations, (
        "Forbidden import lines found:\n  "
        + "\n  ".join(f"{f}:{n}: {l}" for f, n, l in violations)
    )


# ---------------------------------------------------------------------------
# Runtime transitive-import check (subprocess)
# ---------------------------------------------------------------------------


_RUNTIME_FORBIDDEN_MODULES: tuple[str, ...] = (
    "PHX2.services",
    "PHX2.dispatch",
    "PHX2.integrations",
    "PHX2.filters",
    "PHX2.stage16a",
    "PHX2.stage16b",
    "PHX2.db.repositories",
    "PHX2.db.connection",
    "PHX2.config",
    "PHX2.config.settings",
    "PHX2.models",
    "PHX2.models.enums",
    "PHX2.analysis",
)


_RUNTIME_PROBE = textwrap.dedent(
    """
    import sys
    import PHX2.stage17
    import PHX2.stage17.errors
    import PHX2.stage17.models
    import PHX2.stage17.windows
    import PHX2.stage17.labels
    import PHX2.stage17.readers
    import PHX2.stage17.metrics
    import PHX2.stage17.writers
    import PHX2.stage17.manifest
    import PHX2.stage17.cli

    forbidden = {forbidden!r}
    leaked = sorted(m for m in forbidden if m in sys.modules)
    if leaked:
        sys.stdout.write("LEAKED " + repr(leaked))
        sys.exit(2)
    sys.stdout.write("CLEAN")
    """
)


def test_runtime_imports_do_not_load_forbidden_modules() -> None:
    """Spawn a fresh Python interpreter, import the full Stage 17
    surface, and assert no forbidden module is loaded transitively."""

    probe = _RUNTIME_PROBE.format(forbidden=_RUNTIME_FORBIDDEN_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"runtime probe failed.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "CLEAN", result.stdout


@pytest.mark.parametrize(
    "module_name",
    [
        "PHX2.stage17",
        "PHX2.stage17.errors",
        "PHX2.stage17.models",
        "PHX2.stage17.windows",
        "PHX2.stage17.labels",
        "PHX2.stage17.readers",
        "PHX2.stage17.metrics",
        "PHX2.stage17.writers",
        "PHX2.stage17.manifest",
        "PHX2.stage17.cli",
    ],
)
def test_runtime_import_of_single_module_is_clean(module_name: str) -> None:
    """Per-module probe: importing each Stage 17 surface module in a
    fresh interpreter must not load any forbidden module."""

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
        f"importing {module_name!r} leaks: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "CLEAN"
