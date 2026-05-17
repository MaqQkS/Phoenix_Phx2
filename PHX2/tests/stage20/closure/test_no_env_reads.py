"""Stage 20.4 -- no os.environ access or os.getenv calls anywhere in
PHX2/stage20/closure/ (inner scope check)."""

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


def test_phx2_stage20_closure_has_no_env_reads():
    """No ``os.environ`` access or ``os.getenv(...)`` calls in any
    file under PHX2/stage20/closure/ (env reads are an inner-only
    concern, tied to E2037 in the checklist)."""
    result = ca.audit_codebase(_repo_root())
    assert result.env_reads_in_closure == (), (
        f"env reads in closure/: {result.env_reads_in_closure}"
    )
