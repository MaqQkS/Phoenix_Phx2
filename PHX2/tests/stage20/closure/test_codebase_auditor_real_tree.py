"""Stage 20.4 codebase auditor -- real PHX2/stage20/ tree audit.

Runs ``audit_codebase`` against the actual repo and asserts the
current Stage 20 source tree passes cleanly: zero forbidden
imports across inner + outer scope, zero env reads / subprocess
/ sqlite in closure/, zero blocking tokens, zero warning tokens.

If any of these assertions fails, the test message dumps the
offending hits so the operator can see what regressed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage20.closure import codebase_auditor as ca


def _repo_root() -> Path:
    """Return the repo root by walking up from this test file until
    PHX2/stage20/closure/__init__.py is found."""
    p = Path(__file__).resolve()
    for ancestor in [p, *p.parents]:
        candidate = (
            ancestor / "PHX2" / "stage20" / "closure" / "__init__.py"
        )
        if candidate.is_file():
            return ancestor
    raise RuntimeError(
        f"could not locate PHX2 repo root from {p}"
    )


def test_real_repo_root_resolution_works():
    """Sanity: the helper resolves a directory that contains the
    expected closure subtree."""
    root = _repo_root()
    assert (root / "PHX2" / "stage20" / "closure").is_dir()
    assert (root / "PHX2" / "stage20" / "__init__.py").is_file()


def test_real_tree_audit_passes_cleanly():
    """The current real PHX2/stage20/ tree must produce zero error
    hits across every bucket. Warning tokens are also asserted
    empty as a baseline (any future addition should be a deliberate
    choice and updated here explicitly)."""
    result = ca.audit_codebase(_repo_root())

    # Error buckets must all be empty.
    assert result.forbidden_network_imports == (), (
        f"forbidden_network_imports: {result.forbidden_network_imports}"
    )
    assert result.forbidden_phoenix1_imports == (), (
        f"forbidden_phoenix1_imports: {result.forbidden_phoenix1_imports}"
    )
    assert result.cross_stage_violations == (), (
        f"cross_stage_violations: {result.cross_stage_violations}"
    )
    assert result.env_reads_in_closure == (), (
        f"env_reads_in_closure: {result.env_reads_in_closure}"
    )
    assert result.subprocess_uses_in_closure == (), (
        f"subprocess_uses_in_closure: "
        f"{result.subprocess_uses_in_closure}"
    )
    assert result.sqlite_imports_in_closure == (), (
        f"sqlite_imports_in_closure: {result.sqlite_imports_in_closure}"
    )
    assert result.blocking_token_hits == (), (
        f"blocking_token_hits: {result.blocking_token_hits}"
    )

    # Baseline: warning_token_hits is empty on the current tree. If
    # a future change introduces a provider name in source, this
    # test will fail and the operator should make a deliberate
    # decision about whether to update the baseline.
    assert result.warning_token_hits == (), (
        f"warning_token_hits (baseline): {result.warning_token_hits}"
    )

    assert result.passed is True


def test_real_tree_audit_scans_nonzero_files():
    """Sanity: inner + outer scope each scanned at least one file."""
    result = ca.audit_codebase(_repo_root())
    assert len(result.inner_files_scanned) >= 1, (
        "expected at least one .py file under PHX2/stage20/closure/"
    )
    assert len(result.outer_files_scanned) >= 1, (
        "expected at least one .py file under PHX2/stage20/ outside closure/"
    )


def test_real_tree_audit_inner_files_all_under_closure():
    """Every inner-scope file path must contain ``/closure/``."""
    result = ca.audit_codebase(_repo_root())
    for path in result.inner_files_scanned:
        assert "/closure/" in path, path


def test_real_tree_audit_outer_files_never_under_closure():
    """Every outer-scope file path must NOT contain ``/closure/``."""
    result = ca.audit_codebase(_repo_root())
    for path in result.outer_files_scanned:
        assert "/closure/" not in path, path
