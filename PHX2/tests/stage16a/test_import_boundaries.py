"""Phase 9: AST-based import boundary checks.

Forward direction: every .py file under ``PHX2/stage16a/`` must NOT import
any module that would couple Stage 16A to the live alert flow:

  * databases / sqlite (PHX2.database, PHX2.db.*, sqlite3)
  * existing services / repositories / filters / models (other than
    PHX2.stage16a.models, which is Stage 16A's own)
  * any prior pipeline stage (PHX2.stage0 .. PHX2.stage15)
  * network libraries (requests, httpx, aiohttp, urllib3, socket)
  * asyncio (Stage 16A is synchronous; no asyncio coroutines)

Reverse direction: no module under ``PHX2/services``, ``PHX2/filters``,
or ``PHX2/dispatch`` may import Stage 16A. This is the structural lock
that guarantees no live decision path can call into Stage 16A and inherit
its observe-only payload as a hard-blocking signal.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


# Repo root: this file lives at PHX2/tests/stage16a/test_import_boundaries.py
# so parents[3] gets us to the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE16A_DIR = REPO_ROOT / "PHX2" / "stage16a"


FORBIDDEN_EXACT: frozenset[str] = frozenset({
    "sqlite3",
    "asyncio",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "socket",
    "PHX2.database",
})

# Any import whose dotted path starts with one of these is forbidden.
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "PHX2.db",            # PHX2.db.*  (connection, migrations, repositories)
    "PHX2.db.",
    "PHX2.services.",
    "PHX2.services",
    "PHX2.filters.",
    "PHX2.filters",
    # PHX2.models.* (but PHX2.stage16a.models is fine and won't match this prefix)
    "PHX2.models.",
    "PHX2.models",
    # Prior-stage modules. PHX2.stage15 is forbidden per locked O3
    # (Stage 16A copies hashing rather than importing).
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


def _collect_imports(py_file: Path) -> set[str]:
    """Walk the AST of ``py_file`` and collect every imported dotted name.

    ``import X`` -> ``X``
    ``import X.Y`` -> ``X.Y``
    ``from X.Y import Z`` -> ``X.Y``
    ``from . import Z`` (relative) -> ignored (always Stage 16A-local)
    """

    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import -- always Stage 16A-local. Ignore.
                continue
            if node.module:
                names.add(node.module)
    return names


def _is_forbidden(module: str) -> tuple[bool, str]:
    """Return ``(forbidden, reason)``.

    Carve out: ``PHX2.stage16a`` and ``PHX2.stage16a.*`` are NOT forbidden
    even though they start with "PHX2.stage". This is checked first.
    """

    if module == "PHX2.stage16a" or module.startswith("PHX2.stage16a."):
        return False, ""

    if module in FORBIDDEN_EXACT:
        return True, f"exact match: {module}"

    for prefix in FORBIDDEN_PREFIXES:
        if module == prefix or module.startswith(prefix + "."):
            return True, f"prefix match: {module} starts with {prefix}"

    return False, ""


# ---------------------------------------------------------------------------
# Forward direction: nothing under PHX2/stage16a/ imports forbidden modules
# ---------------------------------------------------------------------------


def test_stage16a_has_no_forbidden_imports() -> None:
    py_files = sorted(STAGE16A_DIR.rglob("*.py"))
    assert py_files, f"no Python files found under {STAGE16A_DIR}"

    violations: list[tuple[str, str, str]] = []
    for py in py_files:
        for imp in _collect_imports(py):
            forbidden, reason = _is_forbidden(imp)
            if forbidden:
                rel = py.relative_to(REPO_ROOT)
                violations.append((str(rel), imp, reason))

    assert not violations, (
        "Stage 16A modules import forbidden symbols:\n  "
        + "\n  ".join(f"{f}: {imp} ({why})" for f, imp, why in violations)
    )


@pytest.mark.parametrize("py_file", sorted(STAGE16A_DIR.rglob("*.py")))
def test_per_file_no_forbidden_imports(py_file: Path) -> None:
    for imp in _collect_imports(py_file):
        forbidden, reason = _is_forbidden(imp)
        assert not forbidden, (
            f"{py_file.relative_to(REPO_ROOT)} imports forbidden {imp!r}: {reason}"
        )


# ---------------------------------------------------------------------------
# Reverse direction: no alert-flow module imports Stage 16A
# ---------------------------------------------------------------------------


REVERSE_SCAN_DIRS = (
    REPO_ROOT / "PHX2" / "services",
    REPO_ROOT / "PHX2" / "filters",
    REPO_ROOT / "PHX2" / "dispatch",
    REPO_ROOT / "PHX2" / "renderers",
    REPO_ROOT / "PHX2" / "integrations",
)


def _imports_stage16a(module: str) -> bool:
    return module == "PHX2.stage16a" or module.startswith("PHX2.stage16a.")


def test_no_alert_flow_module_imports_stage16a() -> None:
    """Every .py file under PHX2/services, PHX2/filters, PHX2/dispatch,
    PHX2/renderers, PHX2/integrations must NOT import Stage 16A.

    A failure here is the most serious structural regression possible
    for Stage 16A: it would mean Stage 16A's observe-only payload could
    leak into the live alert flow as a blocking signal."""

    violations: list[tuple[str, str]] = []
    for scan_dir in REVERSE_SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for py in scan_dir.rglob("*.py"):
            for imp in _collect_imports(py):
                if _imports_stage16a(imp):
                    rel = py.relative_to(REPO_ROOT)
                    violations.append((str(rel), imp))

    assert not violations, (
        "Alert-flow modules import Stage 16A (this would break observe-only safety):\n  "
        + "\n  ".join(f"{f}: {imp}" for f, imp in violations)
    )


def test_alert_eligibility_engine_does_not_import_stage16a() -> None:
    """Spec-named module: PHX2.services.alert_eligibility_engine."""

    target = REPO_ROOT / "PHX2" / "services" / "alert_eligibility_engine.py"
    if not target.exists():
        pytest.skip(f"{target} not found")
    for imp in _collect_imports(target):
        assert not _imports_stage16a(imp), (
            f"alert_eligibility_engine imports Stage 16A: {imp!r}"
        )


def test_filter_evaluation_engine_does_not_import_stage16a() -> None:
    """Spec-named module: PHX2.services.filter_evaluation_engine."""

    target = REPO_ROOT / "PHX2" / "services" / "filter_evaluation_engine.py"
    if not target.exists():
        pytest.skip(f"{target} not found")
    for imp in _collect_imports(target):
        assert not _imports_stage16a(imp), (
            f"filter_evaluation_engine imports Stage 16A: {imp!r}"
        )


def test_stage16a_test_files_can_import_freely() -> None:
    """Sanity: this very file imports ``PHX2.stage16a.errors`` indirectly
    via other tests. The boundary check applies to production code under
    ``PHX2/stage16a/`` only -- the test directory is unconstrained."""

    # No assertion needed; just document that the test directory is not
    # covered by the forward-direction check.
    assert STAGE16A_DIR.parts[-2:] == ("PHX2", "stage16a")
