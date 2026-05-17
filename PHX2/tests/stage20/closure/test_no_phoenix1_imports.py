"""Stage 20.4 -- no Phoenix1 imports anywhere in PHX2/stage20/."""

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


def test_phx2_stage20_has_no_phoenix1_imports():
    """Inner + outer scope combined: zero matches for
    ``phoenix1 / Phoenix1 / phx1`` (case-sensitive prefixes)."""
    result = ca.audit_codebase(_repo_root())
    assert result.forbidden_phoenix1_imports == (), (
        f"Phoenix1 import hits: {result.forbidden_phoenix1_imports}"
    )
