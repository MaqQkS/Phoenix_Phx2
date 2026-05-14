"""Stage 19 import-boundary checks.

Locked policy: every file under ``PHX2/stage19/`` MUST NOT import
from any of these prefixes:

  * PHX2.stage17    (Stage 18's source -- and Stage 19 cannot
                     reach across to Stage 17 either; Stage 19's
                     only Stage 17 evidence is the
                     ``stage17_label_preserved`` cell that
                     traveled through Stage 18's review_matrix)
  * PHX2.stage18    (Stage 19 reads Stage 18 artifact files only
                     and duplicates any helper it needs locally)
  * PHX2.stage16a, PHX2.stage16b
  * PHX2.services
  * PHX2.dispatch
  * PHX2.integrations
  * PHX2.filters
  * PHX2.db
  * PHX2.config
  * PHX2.models
  * PHX2.analysis
  * any third-party package not in the standard library

Globally forbidden modules (no DB, no network, no email, no
chat, no concurrency primitives, no async event loop):

  * sqlite3
  * requests, httpx, urllib3
  * socket, smtplib, email
  * discord, slack
  * asyncio, multiprocessing, threading

Subprocess restriction: ``subprocess`` is allowed **only** in
``PHX2/stage19/_git.py``, which does not exist in Phase 19.1.
Until that file is created (Phase 19.3), no Stage 19 production
file may import ``subprocess``.

Production-file set is every ``*.py`` under ``PHX2/stage19/``
plus ``PHX2/scripts/run_stage19_review.py`` (the thin script
shim, created in Phase 19.3). Phase 19.1 has no script shim, so
the set is just the stage19 package files.

Verified two ways (mirroring Stage 18):
  1. Static AST check across every ``*.py`` under
     ``PHX2/stage19/`` (and the script shim once it exists).
  2. Runtime check that spawns a fresh Python interpreter and
     imports each Stage 19 surface module, then asserts no
     forbidden module ended up in ``sys.modules``.

Fixture-module sub-policy (locked from Phase 19.1 onward): the
Stage 19 test fixtures under ``PHX2/tests/stage19/fixtures/``
MUST NOT import ``PHX2.stage17`` or ``PHX2.stage18``. They MAY
import ``PHX2.stage19.*`` -- Phase 19.2+ tests legitimately
exercise Stage 19's own readers / validators / constants against
fixture data.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE19_DIR = REPO_ROOT / "PHX2" / "stage19"
STAGE19_SCRIPT = REPO_ROOT / "PHX2" / "scripts" / "run_stage19_review.py"
FIXTURES_DIR = REPO_ROOT / "PHX2" / "tests" / "stage19" / "fixtures"


# Standard-library modules permitted by Stage 19 source. Keep this
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
    "re",          # _git.py SHA-format check (Phase 19.3)
    "shutil",      # cli.py partial-output cleanup (Phase 19.3)
    "statistics",
    "string",      # printable-char validation (Phase 19.2)
    "subprocess",  # _git.py only (enforced by the per-file check)
    "sys",
    "traceback",
    "typing",
})


# Hard-forbidden Stage 19 PHX2 imports. Listed as exact prefix
# strings; the per-file scan checks ``module == prefix`` or
# ``module.startswith(prefix + ".")``.
FORBIDDEN_PHX2_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage16a",
    "PHX2.stage16b",
    "PHX2.services",
    "PHX2.dispatch",
    "PHX2.integrations",
    "PHX2.filters",
    "PHX2.db",
    "PHX2.config",
    "PHX2.models",
    "PHX2.analysis",
)


# Modules Stage 19 must NEVER import (top-level name match).
# ``email`` is stdlib but listed because Stage 19 has no business
# composing or sending email.
GLOBALLY_FORBIDDEN_MODULES: frozenset[str] = frozenset({
    "sqlite3",
    "requests",
    "httpx",
    "urllib3",
    "socket",
    "smtplib",
    "email",
    "discord",
    "slack",
    "asyncio",
    "multiprocessing",
    "threading",
})


# Subprocess policy: subprocess is allowed only in the dedicated
# ``_git.py`` helper. Every other Stage 19 source file must
# remain subprocess-free. ``_git.py`` does not exist in Phase 19.1
# so this exemption applies to no file yet.
SUBPROCESS_ALLOWED_IN: frozenset[str] = frozenset({"_git.py"})


ALLOWED_PHX2_PREFIXES: tuple[str, ...] = (
    "PHX2.stage19",
)


# Fixture-module-specific forbidden prefixes (locked from Phase
# 19.1 onward). Fixtures must stay independent of the upstream
# stages they model (Stage 17, Stage 18). They MAY freely import
# ``PHX2.stage19.*`` -- Phase 19.2+ tests use Stage 19's own
# readers / validators / constants against fixture data.
FIXTURE_FORBIDDEN_PHX2_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
)


# ---------------------------------------------------------------------------
# File enumeration helpers
# ---------------------------------------------------------------------------


def _stage19_production_files() -> list[Path]:
    files = sorted(STAGE19_DIR.rglob("*.py"))
    if STAGE19_SCRIPT.exists():
        files.append(STAGE19_SCRIPT)
    return files


def _stage19_fixture_files() -> list[Path]:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.rglob("*.py"))


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


# ---------------------------------------------------------------------------
# Static AST checks: production files
# ---------------------------------------------------------------------------


def test_stage19_production_files_exist() -> None:
    files = _stage19_production_files()
    assert files, f"no Python files found under {STAGE19_DIR}"


@pytest.mark.parametrize("py_file", _stage19_production_files())
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


@pytest.mark.parametrize("py_file", _stage19_production_files())
def test_per_file_has_no_globally_forbidden_imports(
    py_file: Path,
) -> None:
    """No Stage 19 source file may import sqlite3, network/email/chat
    libraries, or concurrency primitives."""

    violations: list[str] = []
    for module in _collect_imports(py_file):
        top = module.split(".")[0]
        if top in GLOBALLY_FORBIDDEN_MODULES:
            violations.append(module)
    assert not violations, (
        f"{py_file.relative_to(REPO_ROOT)} imports a globally-forbidden "
        f"module: {violations!r}"
    )


@pytest.mark.parametrize("py_file", _stage19_production_files())
def test_per_file_subprocess_only_in_git_helper(py_file: Path) -> None:
    """``subprocess`` must appear in at most one Stage 19 source
    file: ``PHX2/stage19/_git.py``. Phase 19.1 has no ``_git.py``,
    so subprocess is forbidden in every current production file."""

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


@pytest.mark.parametrize("py_file", _stage19_production_files())
def test_per_file_only_imports_allowed_modules(py_file: Path) -> None:
    """Every imported module must be either a permitted stdlib
    module or a Stage 19 internal."""

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
    return no hits on the forbidden prefixes."""

    import re

    pattern = re.compile(
        r"from\s+PHX2\.(services|dispatch|integrations|filters|stage16a|"
        r"stage16b|stage17|stage18|db|config|models|analysis)"
    )
    violations: list[tuple[str, int, str]] = []
    for py in _stage19_production_files():
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
# Static AST checks: fixture modules
# ---------------------------------------------------------------------------


def test_stage19_fixture_files_exist() -> None:
    files = _stage19_fixture_files()
    assert files, f"no fixture files found under {FIXTURES_DIR}"


@pytest.mark.parametrize("py_file", _stage19_fixture_files())
def test_fixture_per_file_has_no_forbidden_phx2_imports(
    py_file: Path,
) -> None:
    """Fixture modules must not import PHX2.stage17 or PHX2.stage18
    -- they are an independent source of truth for the upstream
    contracts. Imports from PHX2.stage19.* are permitted."""

    violations: list[str] = []
    for module in _collect_imports(py_file):
        for prefix in FIXTURE_FORBIDDEN_PHX2_PREFIXES:
            if module == prefix or module.startswith(prefix + "."):
                violations.append(module)
    assert not violations, (
        f"{py_file.relative_to(REPO_ROOT)} imports forbidden modules: "
        f"{violations!r}"
    )


def test_fixture_sub_policy_does_not_forbid_stage19_imports() -> None:
    """The fixture sub-policy must NOT include ``PHX2.stage19`` --
    Phase 19.2+ tests will legitimately import Stage 19's own
    readers/validators/constants from fixture modules."""

    assert "PHX2.stage19" not in FIXTURE_FORBIDDEN_PHX2_PREFIXES


def test_fixture_sub_policy_locks_stage17_and_stage18() -> None:
    """The fixture sub-policy must include both ``PHX2.stage17``
    and ``PHX2.stage18`` (operator-mandated independence rule)."""

    assert "PHX2.stage17" in FIXTURE_FORBIDDEN_PHX2_PREFIXES
    assert "PHX2.stage18" in FIXTURE_FORBIDDEN_PHX2_PREFIXES


# ---------------------------------------------------------------------------
# Runtime transitive-import check (subprocess)
# ---------------------------------------------------------------------------


_RUNTIME_FORBIDDEN_MODULES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage17.cli",
    "PHX2.stage17.metrics",
    "PHX2.stage17.writers",
    "PHX2.stage17.manifest",
    "PHX2.stage17.readers",
    "PHX2.stage18",
    "PHX2.stage18.cli",
    "PHX2.stage18.classifier",
    "PHX2.stage18.constants",
    "PHX2.stage18.errors",
    "PHX2.stage18.manifest",
    "PHX2.stage18.metrics",
    "PHX2.stage18.readers",
    "PHX2.stage18.writers",
    "PHX2.stage18._git",
    "PHX2.stage16a",
    "PHX2.stage16b",
    "PHX2.services",
    "PHX2.dispatch",
    "PHX2.integrations",
    "PHX2.filters",
    "PHX2.db",
    "PHX2.db.repositories",
    "PHX2.db.connection",
    "PHX2.config",
    "PHX2.config.settings",
    "PHX2.models",
    "PHX2.models.enums",
    "PHX2.analysis",
    "sqlite3",
    "requests",
    "httpx",
    "urllib3",
    "socket",
    "smtplib",
    "email",
    "discord",
    "slack",
    "asyncio",
    "multiprocessing",
    "threading",
)


_RUNTIME_PROBE = textwrap.dedent(
    """
    import sys
    import PHX2.stage19
    import PHX2.stage19.constants
    import PHX2.stage19.errors

    forbidden = {forbidden!r}
    leaked = sorted(m for m in forbidden if m in sys.modules)
    if leaked:
        sys.stdout.write("LEAKED " + repr(leaked))
        sys.exit(2)
    sys.stdout.write("CLEAN")
    """
)


def test_runtime_imports_do_not_load_forbidden_modules() -> None:
    """Spawn a fresh Python interpreter, import the full Stage 19
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
        "PHX2.stage19",
        "PHX2.stage19.constants",
        "PHX2.stage19.errors",
    ],
)
def test_runtime_import_of_single_module_is_clean(module_name: str) -> None:
    """Per-module probe: importing each Stage 19 surface module in
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
