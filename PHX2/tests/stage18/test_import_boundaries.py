"""Stage 18 import-boundary checks.

Locked policy: every file under ``PHX2/stage18/`` MUST NOT import
from any of these prefixes:

  * PHX2.services
  * PHX2.dispatch
  * PHX2.integrations
  * PHX2.filters
  * PHX2.stage16a
  * PHX2.stage16b
  * PHX2.stage17 (Stage 18 reads the artifact files only and
    duplicates any helper it needs locally)
  * PHX2.db (no DB access, period -- not just no repositories)
  * PHX2.config
  * PHX2.models
  * PHX2.analysis
  * any third-party package not in the standard library
  * sqlite3 (Stage 18 has no DB access of any kind)

Subprocess restriction (Phase 18.3 onward): ``subprocess`` is
allowed **only** in ``PHX2/stage18/_git.py``, which owns the
single ``git rev-parse`` helper that captures HEAD into the
manifest. Every other Stage 18 production file must remain
subprocess-free; presence of ``subprocess`` anywhere else
indicates an unintended escape hatch.

Production-file set also includes ``PHX2/scripts/run_stage18_review.py``
(the thin script shim) so the boundary policy reaches the entry
point operators actually invoke.

Verified two ways:
  1. Static AST check across every ``*.py`` under
     ``PHX2/stage18/`` and the Stage 18 script.
  2. Runtime check that spawns a fresh Python interpreter and
     imports each Stage 18 surface module, then asserts no
     forbidden module ended up in ``sys.modules``.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE18_DIR = REPO_ROOT / "PHX2" / "stage18"
STAGE18_SCRIPT = REPO_ROOT / "PHX2" / "scripts" / "run_stage18_review.py"


# Standard-library modules permitted by Stage 18 source. Keep this
# list tight; any non-stdlib third-party import or any unlisted
# stdlib module is a boundary violation.
ALLOWED_STDLIB_MODULES: frozenset[str] = frozenset({
    "__future__",
    "argparse",
    "collections",
    "contextlib",
    "csv",
    "dataclasses",
    "datetime",
    "enum",
    "hashlib",
    "io",
    "json",
    "math",
    "os",
    "pathlib",
    "re",          # _git.py SHA-format check (Phase 18.3)
    "statistics",
    "subprocess",  # _git.py only (enforced by the per-file check)
    "sys",
    "traceback",
    "typing",
})


# Hard-forbidden Stage 18 imports (per the locked spec).
FORBIDDEN_PHX2_PREFIXES: tuple[str, ...] = (
    "PHX2.services",
    "PHX2.dispatch",
    "PHX2.integrations",
    "PHX2.filters",
    "PHX2.stage16a",
    "PHX2.stage16b",
    "PHX2.stage17",
    "PHX2.db",
    "PHX2.config",
    "PHX2.models",
    "PHX2.analysis",
)


# Modules Stage 18 must NEVER import. ``sqlite3`` is the headline
# rule -- Stage 18 has no DB access of any kind.
GLOBALLY_FORBIDDEN_MODULES: frozenset[str] = frozenset({
    "sqlite3",
})


# Phase-18.3 subprocess policy: subprocess is allowed only in the
# dedicated ``_git.py`` helper. Every other Stage 18 source file
# must remain subprocess-free.
SUBPROCESS_ALLOWED_IN: frozenset[str] = frozenset({"_git.py"})


ALLOWED_PHX2_PREFIXES: tuple[str, ...] = (
    "PHX2.stage18",
)


def _stage18_production_files() -> list[Path]:
    files = sorted(STAGE18_DIR.rglob("*.py"))
    if STAGE18_SCRIPT.exists():
        files.append(STAGE18_SCRIPT)
    return files


def _collect_imports(py_file: Path) -> list[str]:
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


def test_stage18_production_files_exist() -> None:
    files = _stage18_production_files()
    assert files, f"no Python files found under {STAGE18_DIR}"


@pytest.mark.parametrize("py_file", _stage18_production_files())
def test_per_file_has_no_forbidden_phx2_imports(py_file: Path) -> None:
    violations: list[str] = []
    for module in _collect_imports(py_file):
        for prefix in FORBIDDEN_PHX2_PREFIXES:
            if module == prefix or module.startswith(prefix + "."):
                violations.append(module)
    assert not violations, (
        f"{py_file.relative_to(REPO_ROOT)} imports forbidden modules: "
        f"{violations!r}"
    )


@pytest.mark.parametrize("py_file", _stage18_production_files())
def test_per_file_has_no_globally_forbidden_imports(
    py_file: Path,
) -> None:
    """No Stage 18 source file may import sqlite3 (or any other
    globally-forbidden module). Stage 18 is a pure file-IO
    sidecar."""

    violations: list[str] = []
    for module in _collect_imports(py_file):
        top = module.split(".")[0]
        if top in GLOBALLY_FORBIDDEN_MODULES:
            violations.append(module)
    assert not violations, (
        f"{py_file.relative_to(REPO_ROOT)} imports a globally-forbidden "
        f"module: {violations!r}"
    )


@pytest.mark.parametrize("py_file", _stage18_production_files())
def test_per_file_subprocess_only_in_git_helper(py_file: Path) -> None:
    """``subprocess`` must appear in at most one Stage 18 source
    file: ``PHX2/stage18/_git.py``. The script shim
    ``run_stage18_review.py`` is also subprocess-free; it just
    delegates to ``PHX2.stage18.cli.main``."""

    imports_subprocess = any(
        module.split(".")[0] == "subprocess"
        for module in _collect_imports(py_file)
    )
    if py_file.name in SUBPROCESS_ALLOWED_IN:
        return
    assert not imports_subprocess, (
        f"{py_file.relative_to(REPO_ROOT)} imports subprocess; "
        f"subprocess is allowed only in: "
        f"{sorted(SUBPROCESS_ALLOWED_IN)}"
    )


@pytest.mark.parametrize("py_file", _stage18_production_files())
def test_per_file_only_imports_allowed_modules(py_file: Path) -> None:
    """Every imported module must be either a permitted stdlib
    module or a Stage 18 internal."""

    violations: list[str] = []
    for module in _collect_imports(py_file):
        if any(
            module == p or module.startswith(p + ".")
            for p in ALLOWED_PHX2_PREFIXES
        ):
            continue
        top = module.split(".")[0]
        if top in ALLOWED_STDLIB_MODULES:
            continue
        violations.append(module)
    assert not violations, (
        f"{py_file.relative_to(REPO_ROOT)} imports modules outside "
        f"the locked allowlist: {violations!r}"
    )


def test_static_grep_for_forbidden_phx2_prefixes() -> None:
    """Audit-required static check: a regex scan of source must
    return no hits on the forbidden prefixes. Mirrors the audit
    grep in the Stage 18 contract."""

    import re

    pattern = re.compile(
        r"from\s+PHX2\.(services|dispatch|integrations|filters|stage16a|"
        r"stage16b|stage17|db|config|models|analysis)"
    )
    violations: list[tuple[str, int, str]] = []
    for py in _stage18_production_files():
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
    "PHX2.stage17",
    "PHX2.stage17.cli",
    "PHX2.stage17.metrics",
    "PHX2.stage17.writers",
    "PHX2.stage17.manifest",
    "PHX2.stage17.readers",
    "PHX2.stage17.labels",
    "PHX2.stage17.windows",
    "PHX2.stage17.models",
    "PHX2.stage17.errors",
    "PHX2.db",
    "PHX2.db.repositories",
    "PHX2.db.connection",
    "PHX2.config",
    "PHX2.config.settings",
    "PHX2.models",
    "PHX2.models.enums",
    "PHX2.analysis",
    "sqlite3",
)


_RUNTIME_PROBE = textwrap.dedent(
    """
    import sys
    import PHX2.stage18
    import PHX2.stage18.constants
    import PHX2.stage18.errors
    import PHX2.stage18.readers
    import PHX2.stage18.metrics
    import PHX2.stage18.classifier
    import PHX2.stage18._git
    import PHX2.stage18.writers
    import PHX2.stage18.manifest
    import PHX2.stage18.cli

    forbidden = {forbidden!r}
    leaked = sorted(m for m in forbidden if m in sys.modules)
    if leaked:
        sys.stdout.write("LEAKED " + repr(leaked))
        sys.exit(2)
    sys.stdout.write("CLEAN")
    """
)


def test_runtime_imports_do_not_load_forbidden_modules() -> None:
    """Spawn a fresh Python interpreter, import the full Stage 18
    surface, and assert no forbidden module is loaded
    transitively."""

    probe = _RUNTIME_PROBE.format(forbidden=_RUNTIME_FORBIDDEN_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"runtime probe failed.\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "CLEAN", result.stdout


@pytest.mark.parametrize(
    "module_name",
    [
        "PHX2.stage18",
        "PHX2.stage18.constants",
        "PHX2.stage18.errors",
        "PHX2.stage18.readers",
        "PHX2.stage18.metrics",
        "PHX2.stage18.classifier",
        "PHX2.stage18._git",
        "PHX2.stage18.writers",
        "PHX2.stage18.manifest",
        "PHX2.stage18.cli",
    ],
)
def test_runtime_import_of_single_module_is_clean(module_name: str) -> None:
    """Per-module probe: importing each Stage 18 surface module in
    a fresh interpreter must not load any forbidden module."""

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
