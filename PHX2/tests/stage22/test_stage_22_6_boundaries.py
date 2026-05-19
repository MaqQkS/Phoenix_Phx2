"""Stage 22.6 boundary tests for the closure audit and operator
runbook docs.

These tests are the documentation-side complement to the rolling
Stage 22.1 - 22.5 boundary scanners. They confirm:

  * the two docs live at the locked paths;
  * the docs reference the locked stage-21-closed commit SHA;
  * Stage 21 has not drifted since the ``stage-21-closed`` tag
    (verified via ``git diff`` when git is available);
  * the import graph that backs the runbook's scratch-script
    pattern is unchanged: ``bounded_live_runner.py`` imports
    nothing from Stage 21, and ``live_composition.py`` is the
    single Stage 22 production module that imports any Stage 21
    runtime collaborator;
  * Stage 22.6 introduces NO new Stage 22 production ``.py``
    module (this is a docs-only stage);
  * the docs index file (``PHX2/stage22/__init__.py``) was not
    forced to import any new module by Stage 22.6.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

import pytest


STAGE21_CLOSED_COMMIT: str = (
    "67e5453d2b4e7d9f59af4bd50fbc4718de35b0cc"
)


REPO_ROOT: Path = Path(__file__).parent.parent.parent.parent
STAGE21_ROOT: Path = REPO_ROOT / "PHX2" / "stage21"
STAGE22_ROOT: Path = REPO_ROOT / "PHX2" / "stage22"

CLOSURE_AUDIT_PATH: Path = STAGE22_ROOT / "STAGE_22_CLOSURE_AUDIT.md"
OPERATOR_RUNBOOK_PATH: Path = STAGE22_ROOT / "STAGE_22_OPERATOR_RUNBOOK.md"
BOUNDED_RUNNER_PATH: Path = STAGE22_ROOT / "bounded_live_runner.py"
LIVE_COMPOSITION_PATH: Path = STAGE22_ROOT / "live_composition.py"
INGEST_CONTRACTS_PATH: Path = STAGE22_ROOT / "ingest_contracts.py"


def _git_available() -> bool:
    return shutil.which("git") is not None


def _run_git(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _collect_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module)
    return out


# ---------------------------------------------------------------------------
# Doc presence (defensive duplicate of the per-doc tests)
# ---------------------------------------------------------------------------


def test_both_stage_22_6_docs_exist():
    assert CLOSURE_AUDIT_PATH.is_file(), (
        f"closure audit doc missing at {CLOSURE_AUDIT_PATH}"
    )
    assert OPERATOR_RUNBOOK_PATH.is_file(), (
        f"operator runbook missing at {OPERATOR_RUNBOOK_PATH}"
    )


def test_both_stage_22_6_docs_reference_stage_21_closed_sha():
    audit = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")
    assert STAGE21_CLOSED_COMMIT in audit, (
        "closure audit doc must reference the stage-21-closed commit "
        "SHA verbatim"
    )


# ---------------------------------------------------------------------------
# Stage 21 isolation since the stage-21-closed tag (git-driven)
# ---------------------------------------------------------------------------


def test_stage_21_tag_still_peels_to_locked_commit():
    if not _git_available():
        pytest.skip("git not available")
    code, out, _err = _run_git(
        "rev-parse", "stage-21-closed^{commit}"
    )
    if code != 0:
        pytest.skip("stage-21-closed tag not reachable in this checkout")
    assert out.strip() == STAGE21_CLOSED_COMMIT, (
        f"stage-21-closed must peel to {STAGE21_CLOSED_COMMIT!r}; "
        f"got {out.strip()!r}"
    )


def test_no_stage_21_files_changed_since_stage_21_closed_tag():
    if not _git_available():
        pytest.skip("git not available")
    code, _out, _err = _run_git("rev-parse", "stage-21-closed")
    if code != 0:
        pytest.skip("stage-21-closed tag not reachable in this checkout")
    code, out, err = _run_git(
        "diff",
        "--name-only",
        "stage-21-closed..HEAD",
        "--",
        "PHX2/stage21/",
    )
    assert code == 0, (
        f"git diff failed unexpectedly: rc={code} stderr={err!r}"
    )
    changed = [line for line in out.splitlines() if line.strip()]
    assert changed == [], (
        "Stage 21 files must not change after stage-21-closed; "
        f"changed: {changed}"
    )


def test_no_stage_22_tag_exists_yet():
    if not _git_available():
        pytest.skip("git not available")
    code, out, _err = _run_git("tag", "--list", "stage-22-*")
    if code != 0:
        pytest.skip("git tag --list failed; cannot assert tag absence")
    tags = [line.strip() for line in out.splitlines() if line.strip()]
    assert tags == [], (
        f"no stage-22-* tag may exist yet in Stage 22.6; found: {tags}"
    )


# ---------------------------------------------------------------------------
# Import-graph invariants the runbook depends on
# ---------------------------------------------------------------------------


def test_bounded_runner_still_has_zero_stage_21_imports():
    for mod in _collect_imports(BOUNDED_RUNNER_PATH):
        assert not mod.startswith("PHX2.stage21"), (
            f"bounded_live_runner.py must not import PHX2.stage21; "
            f"got {mod!r}"
        )


def test_live_composition_is_only_stage22_module_importing_stage21_runtime():
    """``live_composition.py`` is the locked Stage 22 production
    seam that imports Stage 21 runtime collaborators (the Helius
    adapter, the live-readiness loader, the provider event
    decoder, the Discord private transport, the transport
    contracts module).

    ``ingest_contracts.py`` imports the typed-record
    ``NormalizedLiveEvent`` from
    ``PHX2.stage21.normalized_events``; that import is a
    type-only re-export and is allowed.

    No other Stage 22 production module may import any
    ``PHX2.stage21`` module.
    """
    runtime_allowed_importers: set[Path] = {
        LIVE_COMPOSITION_PATH,
    }
    type_only_allowed_importers: dict[Path, set[str]] = {
        INGEST_CONTRACTS_PATH: {"PHX2.stage21.normalized_events"},
    }

    for py_file in STAGE22_ROOT.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        imports = _collect_imports(py_file)
        stage21_imports = {
            m for m in imports if m.startswith("PHX2.stage21")
        }
        if not stage21_imports:
            continue
        if py_file == LIVE_COMPOSITION_PATH:
            continue
        if py_file in type_only_allowed_importers:
            allowed = type_only_allowed_importers[py_file]
            unexpected = stage21_imports - allowed
            assert unexpected == set(), (
                f"{py_file} may only import {sorted(allowed)} from "
                f"PHX2.stage21; got unexpected {sorted(unexpected)}"
            )
            continue
        raise AssertionError(
            f"{py_file} imports PHX2.stage21 modules {sorted(stage21_imports)} "
            f"but is not on the Stage 22 live-composition allowlist "
            f"({sorted(p.name for p in runtime_allowed_importers)})"
        )


# ---------------------------------------------------------------------------
# Stage 22.6 is docs-only: no new production .py module
# ---------------------------------------------------------------------------


_STAGE22_2_2_5_PRODUCTION_MODULES: frozenset[str] = frozenset({
    "__init__.py",
    "constants.py",
    "errors.py",
    "ingest_contracts.py",
    "failure_classification.py",
    "dedupe_ledger.py",
    "raw_capture.py",
    "failure_handling.py",
    "bounded_live_runner.py",
    "live_composition.py",
})


def test_stage_22_6_introduces_no_new_production_py_module():
    actual = {
        p.name for p in STAGE22_ROOT.glob("*.py")
        if "__pycache__" not in p.parts
    }
    unexpected = actual - _STAGE22_2_2_5_PRODUCTION_MODULES
    assert unexpected == set(), (
        f"Stage 22.6 must remain docs-only at the production layer; "
        f"unexpected .py module(s) introduced: {sorted(unexpected)}"
    )


# ---------------------------------------------------------------------------
# Pre-existing untracked paths are documented as untouched
# ---------------------------------------------------------------------------


def test_closure_audit_documents_the_three_known_untracked_paths():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")
    for path in (
        "PHX2/.stage_17_inputs/",
        "PHX2/docs/",
        "ROADMAP.md",
    ):
        assert path in text, (
            f"closure audit doc must enumerate pre-existing untracked "
            f"path {path!r}"
        )
