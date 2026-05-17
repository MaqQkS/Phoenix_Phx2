"""Stage 20.4 -- forbidden blocking-token (E2040) tests.

  * Synthetic source files with True forms of safe_for_live_dispatch
    or live_dispatch_ready trigger E2040 (blocking_token_hits).
  * The closure module itself has zero blocking-token hits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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


def _build_tree(tmp_path: Path, layout: dict) -> Path:
    base = tmp_path / "PHX2" / "stage20"
    base.mkdir(parents=True, exist_ok=True)
    for rel, content in layout.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Synthetic source triggers E2040 (8 locked patterns)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("src", [
    # Direct assignment, both cases of name + True/true.
    "safe_for_live_dispatch = True\n",
    "safe_for_live_dispatch = true\n",
    "SAFE_FOR_LIVE_DISPATCH = True\n",
    "SAFE_FOR_LIVE_DISPATCH = true\n",
    # Type-annotated assignment (per operator patch).
    "safe_for_live_dispatch: bool = True\n",
    "SAFE_FOR_LIVE_DISPATCH: bool = True\n",
    "SAFE_FOR_LIVE_DISPATCH: Final[bool] = True\n",
    # Dict-key form, both quote styles.
    'cfg = {"safe_for_live_dispatch": true}\n',
    "cfg = {'safe_for_live_dispatch': True}\n",
    'cfg = {"SAFE_FOR_LIVE_DISPATCH": true}\n',
    # live_dispatch_ready variants.
    "live_dispatch_ready = True\n",
    "live_dispatch_ready = true\n",
    "LIVE_DISPATCH_READY = True\n",
    "live_dispatch_ready: bool = True\n",
    "LIVE_DISPATCH_READY: bool = True\n",
    'cfg = {"live_dispatch_ready": true}\n',
    "cfg = {'live_dispatch_ready': True}\n",
    'cfg = {"LIVE_DISPATCH_READY": true}\n',
])
def test_each_blocking_pattern_triggers(tmp_path: Path, src):
    repo = _build_tree(tmp_path, {"planted.py": src})
    result = ca.audit_codebase(repo)
    assert len(result.blocking_token_hits) >= 1, src
    assert result.passed is False


def test_blocking_token_records_file_line_and_severity(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "planted.py": (
            "# comment\n"
            "x = 0\n"
            "safe_for_live_dispatch = True\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert len(result.blocking_token_hits) == 1
    hit = result.blocking_token_hits[0]
    assert hit.severity == "error"
    assert hit.line == 3
    assert "planted.py" in hit.file


def test_blocking_pattern_covers_type_annotated_assignment(tmp_path: Path):
    """Per operator patch: the locked v0 regex MUST catch type-annotated
    assignments like ``safe_for_live_dispatch: bool = True`` and the
    uppercase variant ``SAFE_FOR_LIVE_DISPATCH: bool = True``. The
    previous gap is now closed by the case-insensitive identifier
    regex with a ``:[^=\\n]*=`` branch."""
    repo = _build_tree(tmp_path, {
        "planted_lower.py": "safe_for_live_dispatch: bool = True\n",
        "planted_upper.py": "SAFE_FOR_LIVE_DISPATCH: bool = True\n",
    })
    result = ca.audit_codebase(repo)
    files_hit = {h.file for h in result.blocking_token_hits}
    assert any("planted_lower.py" in f for f in files_hit)
    assert any("planted_upper.py" in f for f in files_hit)
    assert result.passed is False


def test_blocking_pattern_typed_assignment_with_false_does_not_match(
    tmp_path: Path,
):
    """Sanity check on the ``:[^=\\n]*=`` branch: a typed assignment
    with ``= False`` must NOT trip the blocking scan even though it
    matches the colon-then-equals structure."""
    repo = _build_tree(tmp_path, {
        "planted.py": (
            "safe_for_live_dispatch: bool = False\n"
            "SAFE_FOR_LIVE_DISPATCH: bool = False\n"
            "live_dispatch_ready: bool = False\n"
            "LIVE_DISPATCH_READY: bool = False\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert result.blocking_token_hits == ()
    assert result.passed is True


def test_blocking_pattern_typed_annotation_without_value_does_not_match(
    tmp_path: Path,
):
    """``x: bool`` (annotation, no assignment value) must NOT trip
    the blocking scan: the regex requires ``= True`` or ``: True``
    at the end."""
    repo = _build_tree(tmp_path, {
        "planted.py": (
            "class C:\n"
            "    safe_for_live_dispatch: bool\n"
            "    SAFE_FOR_LIVE_DISPATCH: bool\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert result.blocking_token_hits == ()


def test_blocking_patterns_no_false_match_on_safety_false(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "planted.py": (
            "safe_for_live_dispatch = False\n"
            "live_dispatch_ready = False\n"
            'cfg = {"safe_for_live_dispatch": false}\n'
            'cfg2 = {"live_dispatch_ready": false}\n'
        ),
    })
    result = ca.audit_codebase(repo)
    assert result.blocking_token_hits == ()
    assert result.passed is True


def test_blocking_patterns_no_match_on_unrelated_true_assignments(
    tmp_path: Path,
):
    repo = _build_tree(tmp_path, {
        "planted.py": (
            "x = True\n"
            "some_other_flag = True\n"
            "safe_for_live_dispatch_not_false = True\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert result.blocking_token_hits == ()


# ---------------------------------------------------------------------------
# Real closure subtree has zero blocking-token hits
# ---------------------------------------------------------------------------


def test_real_phx2_stage20_source_has_no_blocking_token_hits():
    """The current PHX2/stage20/ tree must NOT contain any blocking
    pattern (templates/ is auto-excluded but absent in Phase 3)."""
    result = ca.audit_codebase(_repo_root())
    assert result.blocking_token_hits == (), (
        f"blocking token hits in PHX2/stage20/: "
        f"{result.blocking_token_hits}"
    )
