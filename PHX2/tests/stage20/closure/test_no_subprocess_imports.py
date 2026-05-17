"""Stage 20.4 -- no subprocess (or sqlite/aiosqlite) imports in
PHX2/stage20/closure/."""

from __future__ import annotations

from pathlib import Path

from PHX2.stage20.closure import codebase_auditor as ca


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for ancestor in [p, *p.parents]:
        candidate = (
            ancestor / "PHX2" / "stage20" / "closure" / "__init__.py"
        )
        if candidate.is_file():
            return ancestor
    raise RuntimeError(f"could not locate PHX2 repo root from {p}")


def test_phx2_stage20_closure_has_no_subprocess_imports():
    """No ``import subprocess`` (or submodule) anywhere under
    PHX2/stage20/closure/."""
    result = ca.audit_codebase(_repo_root())
    assert result.subprocess_uses_in_closure == (), (
        f"subprocess imports in closure/: "
        f"{result.subprocess_uses_in_closure}"
    )


def test_phx2_stage20_closure_has_no_sqlite_imports():
    """No ``import sqlite3`` / ``import aiosqlite`` anywhere under
    PHX2/stage20/closure/ (also an inner-only concern, surfaced
    in the same checklist row C20_4_20 as subprocess)."""
    result = ca.audit_codebase(_repo_root())
    assert result.sqlite_imports_in_closure == (), (
        f"sqlite imports in closure/: "
        f"{result.sqlite_imports_in_closure}"
    )
