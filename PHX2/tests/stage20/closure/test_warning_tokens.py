"""Stage 20.4 -- warning-token (W2025) tests.

  * Synthetic source files with provider names trigger W2025 hits
    (warning_token_hits) but do NOT flip ``passed`` to False.
  * The closure module itself has zero warning-token hits
    (baseline -- a future deliberate addition would update this).
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
# Synthetic source triggers W2025 (5 locked warning patterns)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("token,src", [
    ("webhook_url", "webhook_url = 'http://x'\n"),
    ("api_key", "api_key = 'secret'\n"),
    ("private_key", "private_key = 'p'\n"),
    ("HELIUS", "HELIUS = 'h'\n"),
    ("BIRDEYE", "BIRDEYE = 'b'\n"),
])
def test_each_warning_pattern_triggers(tmp_path: Path, token, src):
    repo = _build_tree(tmp_path, {"planted.py": src})
    result = ca.audit_codebase(repo)
    matched = [h for h in result.warning_token_hits if h.token == token]
    assert len(matched) == 1
    assert matched[0].severity == "warning"


def test_warning_tokens_do_not_flip_passed_false(tmp_path: Path):
    """W2025 is non-blocking; warning_token_hits must not affect
    ``passed``."""
    repo = _build_tree(tmp_path, {
        "planted.py": (
            "webhook_url = 'x'\n"
            "api_key = 'y'\n"
            "HELIUS = 'h'\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert len(result.warning_token_hits) >= 3
    assert result.passed is True


def test_warning_token_records_file_line_and_severity(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "planted.py": "# header\nx = 1\napi_key = 'secret'\n",
    })
    result = ca.audit_codebase(repo)
    matched = [h for h in result.warning_token_hits if h.token == "api_key"]
    assert len(matched) == 1
    hit = matched[0]
    assert hit.severity == "warning"
    assert hit.line == 3
    assert "planted.py" in hit.file


def test_warning_pattern_word_boundaries_reject_subword_matches(
    tmp_path: Path,
):
    """``\\bapi_key\\b`` must not match ``my_api_keys`` or
    ``api_keystone``."""
    repo = _build_tree(tmp_path, {
        "planted.py": (
            "my_api_keys = ['a']\n"
            "api_keystone = 1\n"
            "BIRDEYESCAN = 'no_match'\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert result.warning_token_hits == ()


# ---------------------------------------------------------------------------
# Real closure subtree baseline
# ---------------------------------------------------------------------------


def test_real_phx2_stage20_source_has_no_warning_token_hits():
    """Baseline: the current PHX2/stage20/ tree has zero W2025 hits.
    Any future addition of a provider name in source should update
    this assertion deliberately."""
    result = ca.audit_codebase(_repo_root())
    assert result.warning_token_hits == (), (
        f"warning token hits in PHX2/stage20/: "
        f"{result.warning_token_hits}"
    )
