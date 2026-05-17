"""Stage 20.4 codebase auditor tests (synthetic trees).

Cover:

  * Empty tree -> passed=True with empty buckets.
  * Outer-scope hits: network / dispatch / grpc / Phoenix1 /
    cross-stage; prefix matching with ``\\bgrpc\\b`` vs grpcio_fake.
  * Inner-scope hits: network / Phoenix1 / dotenv / sqlite /
    subprocess / git / env-reads; cross-stage NOT checked
    in inner scope (per locked spec C.5).
  * Token scan: blocking + warning patterns; templates/ excluded.
  * File walks deterministic; __pycache__ excluded.
  * passed=True iff every error bucket empty;
    warning_token_hits does not flip passed.
  * Forward-slash normalization on file path strings.
  * AST self-audit of codebase_auditor.py.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from PHX2.stage20.closure import codebase_auditor as ca
from PHX2.stage20.closure.models import (
    CodebaseAuditResult,
    ImportHit,
    TokenHit,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _build_tree(tmp_path: Path, layout: dict) -> Path:
    """Build a synthetic PHX2/stage20/ tree under tmp_path.

    ``layout`` is a dict mapping ``"path/relative/to/PHX2/stage20"``
    -> source string. Returns ``tmp_path`` (to use as ``repo_root``).
    """

    base = tmp_path / "PHX2" / "stage20"
    base.mkdir(parents=True, exist_ok=True)
    for rel, content in layout.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Empty / baseline trees
# ---------------------------------------------------------------------------


def test_empty_tree_returns_passed_true(tmp_path: Path):
    repo = _build_tree(tmp_path, {})
    result = ca.audit_codebase(repo)
    assert isinstance(result, CodebaseAuditResult)
    assert result.passed is True
    assert result.forbidden_network_imports == ()
    assert result.forbidden_phoenix1_imports == ()
    assert result.cross_stage_violations == ()
    assert result.env_reads_in_closure == ()
    assert result.subprocess_uses_in_closure == ()
    assert result.sqlite_imports_in_closure == ()
    assert result.blocking_token_hits == ()
    assert result.warning_token_hits == ()


def test_benign_tree_with_stdlib_only_imports_passes(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "outer_file.py": "import json\nimport hashlib\nx = 1\n",
        "closure/inner_file.py": "from pathlib import Path\n",
    })
    result = ca.audit_codebase(repo)
    assert result.passed is True


# ---------------------------------------------------------------------------
# Outer-scope hits
# ---------------------------------------------------------------------------


def test_outer_scope_catches_requests_import(tmp_path: Path):
    repo = _build_tree(tmp_path, {"some_module.py": "import requests\n"})
    result = ca.audit_codebase(repo)
    assert result.passed is False
    assert len(result.forbidden_network_imports) == 1
    hit = result.forbidden_network_imports[0]
    assert hit.module == "requests"
    assert hit.reason == "network_client"
    assert "/PHX2/stage20/some_module.py" in hit.file
    assert hit.line == 1


@pytest.mark.parametrize("module_name", [
    "httpx", "aiohttp", "urllib3", "websockets",
])
def test_outer_scope_catches_network_clients(tmp_path: Path, module_name):
    repo = _build_tree(tmp_path, {
        "m.py": f"import {module_name}\n",
    })
    result = ca.audit_codebase(repo)
    modules = [h.module for h in result.forbidden_network_imports]
    assert module_name in modules


@pytest.mark.parametrize("dispatch", [
    "discord", "telegram", "telethon", "pyrogram",
])
def test_outer_scope_catches_dispatch_clients(tmp_path: Path, dispatch):
    repo = _build_tree(tmp_path, {"m.py": f"import {dispatch}\n"})
    result = ca.audit_codebase(repo)
    modules = [h.module for h in result.forbidden_network_imports]
    reasons = [h.reason for h in result.forbidden_network_imports]
    assert dispatch in modules
    assert "dispatch_client" in reasons


def test_outer_scope_catches_grpc_submodule_by_prefix(tmp_path: Path):
    repo = _build_tree(tmp_path, {"m.py": "import grpc.aio\n"})
    result = ca.audit_codebase(repo)
    assert any(
        h.module == "grpc.aio" and h.reason == "grpc"
        for h in result.forbidden_network_imports
    )


def test_outer_scope_does_not_match_grpcio_fake_against_grpc(tmp_path: Path):
    """``grpcio_fake`` must NOT match the ``grpc`` prefix (locked spec
    requires prefix-followed-by-'.' matching)."""
    repo = _build_tree(tmp_path, {"m.py": "import grpcio_fake\n"})
    result = ca.audit_codebase(repo)
    assert result.forbidden_network_imports == ()
    assert result.passed is True


@pytest.mark.parametrize("phoenix_name", [
    "phoenix1", "Phoenix1", "phx1",
])
def test_outer_scope_catches_phoenix1_imports(tmp_path: Path, phoenix_name):
    repo = _build_tree(tmp_path, {"m.py": f"import {phoenix_name}\n"})
    result = ca.audit_codebase(repo)
    assert any(
        h.module == phoenix_name
        for h in result.forbidden_phoenix1_imports
    )


def test_outer_scope_phoenix1_match_is_case_sensitive(tmp_path: Path):
    """``PHOENIX1`` (all caps) must NOT match the case-sensitive list."""
    repo = _build_tree(tmp_path, {"m.py": "import PHOENIX1\n"})
    result = ca.audit_codebase(repo)
    assert result.forbidden_phoenix1_imports == ()


def test_outer_scope_catches_cross_stage_from_import(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "m.py": "from PHX2.stage17 import something\n",
    })
    result = ca.audit_codebase(repo)
    assert len(result.cross_stage_violations) == 1
    hit = result.cross_stage_violations[0]
    assert hit.module == "PHX2.stage17"
    assert hit.reason == "cross_stage"


@pytest.mark.parametrize("module", [
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage17.submodule",
    "PHX2.stage18.foo.bar",
])
def test_outer_scope_catches_cross_stage_prefix_or_exact(
    tmp_path: Path, module,
):
    repo = _build_tree(tmp_path, {
        "m.py": f"from {module} import x\n",
    })
    result = ca.audit_codebase(repo)
    assert any(
        h.module == module for h in result.cross_stage_violations
    )


def test_outer_scope_ignores_other_phx2_paths(tmp_path: Path):
    """``PHX2.stage20.*`` and ``PHX2.stage8.*`` are NOT cross-stage
    violations (only 17/18/19 are forbidden)."""
    repo = _build_tree(tmp_path, {
        "m.py": (
            "from PHX2.stage20.something import x\n"
            "from PHX2.stage8.other import y\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert result.cross_stage_violations == ()


def test_outer_scope_does_not_check_subprocess_or_sqlite(tmp_path: Path):
    """Outer scope explicitly does NOT check subprocess / sqlite /
    git / dotenv / env-reads. They are inner-only concerns."""
    repo = _build_tree(tmp_path, {
        "m.py": (
            "import subprocess\n"
            "import sqlite3\n"
            "import git\n"
            "import dotenv\n"
            "import os\n"
            "x = os.environ.get('A')\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert result.forbidden_network_imports == ()
    assert result.subprocess_uses_in_closure == ()
    assert result.sqlite_imports_in_closure == ()
    assert result.env_reads_in_closure == ()


# ---------------------------------------------------------------------------
# Inner-scope hits
# ---------------------------------------------------------------------------


def test_inner_scope_catches_network_import(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "closure/foo.py": "import requests\n",
    })
    result = ca.audit_codebase(repo)
    assert any(
        h.module == "requests" and h.reason == "network_client"
        for h in result.forbidden_network_imports
    )


def test_inner_scope_catches_subprocess(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "closure/foo.py": "import subprocess\n",
    })
    result = ca.audit_codebase(repo)
    assert len(result.subprocess_uses_in_closure) == 1
    hit = result.subprocess_uses_in_closure[0]
    assert hit.module == "subprocess"
    assert hit.reason == "subprocess"
    assert result.passed is False


def test_inner_scope_catches_sqlite3(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "closure/foo.py": "import sqlite3\n",
    })
    result = ca.audit_codebase(repo)
    assert len(result.sqlite_imports_in_closure) == 1
    assert result.sqlite_imports_in_closure[0].module == "sqlite3"


def test_inner_scope_catches_aiosqlite(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "closure/foo.py": "import aiosqlite\n",
    })
    result = ca.audit_codebase(repo)
    assert any(
        h.module == "aiosqlite" for h in result.sqlite_imports_in_closure
    )


def test_inner_scope_lumps_dotenv_into_network_bucket(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "closure/foo.py": "import dotenv\n",
    })
    result = ca.audit_codebase(repo)
    # Per locked CodebaseAuditResult field set, dotenv lands in
    # forbidden_network_imports with reason="dotenv".
    assert any(
        h.module == "dotenv" and h.reason == "dotenv"
        for h in result.forbidden_network_imports
    )


@pytest.mark.parametrize("git_mod", ["git", "pygit2", "dulwich"])
def test_inner_scope_lumps_git_modules_into_network_bucket(
    tmp_path: Path, git_mod,
):
    repo = _build_tree(tmp_path, {
        "closure/foo.py": f"import {git_mod}\n",
    })
    result = ca.audit_codebase(repo)
    assert any(
        h.module == git_mod and h.reason == "git"
        for h in result.forbidden_network_imports
    )


def test_inner_scope_catches_phoenix1(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "closure/foo.py": "import phoenix1\n",
    })
    result = ca.audit_codebase(repo)
    assert len(result.forbidden_phoenix1_imports) == 1


def test_inner_scope_catches_os_environ_access(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "closure/foo.py": (
            "import os\n"
            "x = os.environ['VAR']\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert len(result.env_reads_in_closure) >= 1
    assert any(
        h.module == "os.environ" and h.reason == "env_read"
        for h in result.env_reads_in_closure
    )
    assert result.passed is False


def test_inner_scope_catches_os_getenv_call(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "closure/foo.py": (
            "import os\n"
            "x = os.getenv('VAR')\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert any(
        h.module == "os.getenv" and h.reason == "env_read"
        for h in result.env_reads_in_closure
    )


@pytest.mark.parametrize("stage_prefix", [
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
])
def test_inner_scope_catches_cross_stage_imports(
    tmp_path: Path, stage_prefix,
):
    """Per operator patch: the inner scope (closure/) MUST hard-fail
    on cross-stage imports (E2039), same as the outer scope. AST
    self-audit tests in test_codebase_auditor / test_input_loader
    are kept as defense-in-depth, but the auditor itself is the
    primary enforcement."""
    repo = _build_tree(tmp_path, {
        "closure/foo.py": f"from {stage_prefix} import x\n",
    })
    result = ca.audit_codebase(repo)
    assert any(
        h.module == stage_prefix and h.reason == "cross_stage"
        for h in result.cross_stage_violations
    ), result.cross_stage_violations
    assert result.passed is False


def test_inner_scope_cross_stage_submodule_prefix_match(tmp_path: Path):
    """``from PHX2.stage18.submodule import x`` in closure/ must
    also trigger E2039 (prefix-then-dot match)."""
    repo = _build_tree(tmp_path, {
        "closure/foo.py": "from PHX2.stage18.foo.bar import x\n",
    })
    result = ca.audit_codebase(repo)
    assert any(
        h.module == "PHX2.stage18.foo.bar"
        for h in result.cross_stage_violations
    )


def test_cross_stage_bucket_combines_inner_and_outer_hits(tmp_path: Path):
    """A repo with BOTH an inner-scope and outer-scope cross-stage
    import yields two entries in ``cross_stage_violations``."""
    repo = _build_tree(tmp_path, {
        "closure/inner_bad.py": "from PHX2.stage17 import a\n",
        "outer_bad.py": "from PHX2.stage19 import b\n",
    })
    result = ca.audit_codebase(repo)
    modules = sorted(h.module for h in result.cross_stage_violations)
    assert modules == ["PHX2.stage17", "PHX2.stage19"]


# ---------------------------------------------------------------------------
# Token scan
# ---------------------------------------------------------------------------


def test_token_scan_catches_blocking_safe_for_live_dispatch_true(
    tmp_path: Path,
):
    repo = _build_tree(tmp_path, {
        "m.py": "safe_for_live_dispatch = True\n",
    })
    result = ca.audit_codebase(repo)
    assert len(result.blocking_token_hits) == 1
    hit = result.blocking_token_hits[0]
    assert "safe_for_live_dispatch" in hit.token
    assert hit.severity == "error"
    assert hit.line == 1
    assert result.passed is False


def test_token_scan_catches_blocking_live_dispatch_ready_json_true(
    tmp_path: Path,
):
    repo = _build_tree(tmp_path, {
        "m.py": 'x = {"live_dispatch_ready": true}\n',
    })
    result = ca.audit_codebase(repo)
    assert any(
        "live_dispatch_ready" in h.token
        for h in result.blocking_token_hits
    )


def test_token_scan_does_not_catch_false_literal(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "m.py": (
            "safe_for_live_dispatch = False\n"
            'live_dispatch_ready_dict = {"live_dispatch_ready": false}\n'
        ),
    })
    result = ca.audit_codebase(repo)
    assert result.blocking_token_hits == ()


def test_token_scan_does_not_match_safe_for_live_dispatch_not_false(
    tmp_path: Path,
):
    """The literal ``safe_for_live_dispatch_not_false`` (E2022 code
    name) must NOT trip any blocking pattern -- word boundary fails
    because of the trailing ``_not_false``."""
    repo = _build_tree(tmp_path, {
        "m.py": 'NAMES = {"E2022": "safe_for_live_dispatch_not_false"}\n',
    })
    result = ca.audit_codebase(repo)
    assert result.blocking_token_hits == ()


@pytest.mark.parametrize("token", [
    "webhook_url", "api_key", "private_key", "HELIUS", "BIRDEYE",
])
def test_token_scan_catches_warning_tokens(tmp_path: Path, token):
    repo = _build_tree(tmp_path, {
        "m.py": f"{token} = 'x'\n",
    })
    result = ca.audit_codebase(repo)
    matched = [h for h in result.warning_token_hits if h.token == token]
    assert len(matched) == 1
    assert matched[0].severity == "warning"


def test_warning_token_hits_do_not_flip_passed_to_false(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "m.py": "api_key = 'secret'\n",
    })
    result = ca.audit_codebase(repo)
    assert len(result.warning_token_hits) >= 1
    assert result.passed is True


def test_token_scan_excludes_templates_subtree(tmp_path: Path):
    """Token scan must skip any file whose path contains
    ``/templates/`` (the spec's locked exclusion). This test plants
    a ``.py`` file inside a templates/ directory so we can prove
    the path-substring exclusion fires (real templates are .md.tmpl
    files; Phase 5 builds them)."""

    repo = _build_tree(tmp_path, {
        "closure/templates/decoy.py": "safe_for_live_dispatch = True\n",
        "closure/regular.py": "ok = True\n",
    })
    result = ca.audit_codebase(repo)
    # No blocking hit because the templates file was excluded from
    # the token scan.
    assert all(
        "/templates/" not in h.file for h in result.blocking_token_hits
    )
    assert result.blocking_token_hits == ()


def test_token_scan_emits_line_numbers_and_context(tmp_path: Path):
    src = (
        "# header line\n"
        "x = 1\n"
        "safe_for_live_dispatch = True  # planted violation\n"
    )
    repo = _build_tree(tmp_path, {"m.py": src})
    result = ca.audit_codebase(repo)
    assert len(result.blocking_token_hits) == 1
    h = result.blocking_token_hits[0]
    assert h.line == 3
    assert "safe_for_live_dispatch" in h.context


# ---------------------------------------------------------------------------
# Determinism + file walking
# ---------------------------------------------------------------------------


def test_file_walk_excludes_pycache(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "real_module.py": "x = 1\n",
        "__pycache__/cached.py": "import requests\n",
        "closure/inner.py": "y = 2\n",
        "closure/__pycache__/inner_cached.py": "import requests\n",
    })
    result = ca.audit_codebase(repo)
    # __pycache__ files must not appear in either scan list.
    all_scanned = result.inner_files_scanned + result.outer_files_scanned
    assert all("__pycache__" not in p for p in all_scanned)
    # And no imports from those cache files leaked through.
    assert result.forbidden_network_imports == ()


def test_file_walk_returns_sorted_order(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "z_last.py": "x = 1\n",
        "a_first.py": "y = 2\n",
        "m_middle.py": "z = 3\n",
    })
    result = ca.audit_codebase(repo)
    outer_names = [Path(p).name for p in result.outer_files_scanned]
    assert outer_names == sorted(outer_names)


def test_outer_walk_excludes_closure_subtree(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "outer_only.py": "x = 1\n",
        "closure/inner_only.py": "y = 2\n",
    })
    result = ca.audit_codebase(repo)
    assert any(
        "outer_only.py" in p for p in result.outer_files_scanned
    )
    assert not any(
        "inner_only.py" in p for p in result.outer_files_scanned
    )
    assert any(
        "inner_only.py" in p for p in result.inner_files_scanned
    )


def test_inner_walk_targets_only_closure_subtree(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "not_closure.py": "x = 1\n",
        "closure/yes.py": "y = 2\n",
        "closure/sub/deep.py": "z = 3\n",
    })
    result = ca.audit_codebase(repo)
    inner_names = [Path(p).name for p in result.inner_files_scanned]
    assert "yes.py" in inner_names
    assert "deep.py" in inner_names
    assert "not_closure.py" not in inner_names


def test_file_path_strings_use_forward_slashes(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "outer.py": "import requests\n",
        "closure/inner.py": "import subprocess\n",
    })
    result = ca.audit_codebase(repo)
    for hit in result.forbidden_network_imports:
        assert "\\" not in hit.file
    for hit in result.subprocess_uses_in_closure:
        assert "\\" not in hit.file
    for path in result.inner_files_scanned + result.outer_files_scanned:
        assert "\\" not in path


def test_audit_codebase_returns_namedtuple_with_tuple_buckets(tmp_path: Path):
    repo = _build_tree(tmp_path, {"x.py": "z = 1\n"})
    result = ca.audit_codebase(repo)
    assert isinstance(result, CodebaseAuditResult)
    for field in (
        "inner_files_scanned",
        "outer_files_scanned",
        "forbidden_network_imports",
        "forbidden_phoenix1_imports",
        "cross_stage_violations",
        "env_reads_in_closure",
        "subprocess_uses_in_closure",
        "sqlite_imports_in_closure",
        "blocking_token_hits",
        "warning_token_hits",
    ):
        assert isinstance(getattr(result, field), tuple), field


# ---------------------------------------------------------------------------
# Passed semantics
# ---------------------------------------------------------------------------


def test_passed_true_when_only_warnings_present(tmp_path: Path):
    """warning_token_hits MUST NOT flip passed to False."""
    repo = _build_tree(tmp_path, {
        "m.py": "webhook_url = 'http://x'\n",
    })
    result = ca.audit_codebase(repo)
    assert len(result.warning_token_hits) == 1
    assert result.passed is True


@pytest.mark.parametrize("layout,bucket", [
    (
        {"outer.py": "import requests\n"},
        "forbidden_network_imports",
    ),
    (
        {"outer.py": "import phoenix1\n"},
        "forbidden_phoenix1_imports",
    ),
    (
        {"outer.py": "from PHX2.stage17 import x\n"},
        "cross_stage_violations",
    ),
    (
        {"closure/inner.py": "import subprocess\n"},
        "subprocess_uses_in_closure",
    ),
    (
        {"closure/inner.py": "import sqlite3\n"},
        "sqlite_imports_in_closure",
    ),
    (
        {"closure/inner.py": "import os\nx = os.environ['A']\n"},
        "env_reads_in_closure",
    ),
    (
        {"m.py": "safe_for_live_dispatch = True\n"},
        "blocking_token_hits",
    ),
])
def test_passed_false_when_any_error_bucket_nonempty(
    tmp_path: Path, layout, bucket,
):
    repo = _build_tree(tmp_path, layout)
    result = ca.audit_codebase(repo)
    assert len(getattr(result, bucket)) >= 1, bucket
    assert result.passed is False


# ---------------------------------------------------------------------------
# Multiple hits accumulate per file
# ---------------------------------------------------------------------------


def test_multiple_hits_in_one_file_all_recorded(tmp_path: Path):
    repo = _build_tree(tmp_path, {
        "closure/bad.py": (
            "import requests\n"
            "import sqlite3\n"
            "import subprocess\n"
            "import os\n"
            "x = os.environ.get('A')\n"
            "y = os.getenv('B')\n"
        ),
    })
    result = ca.audit_codebase(repo)
    assert len(result.forbidden_network_imports) >= 1
    assert len(result.sqlite_imports_in_closure) == 1
    assert len(result.subprocess_uses_in_closure) == 1
    # os.environ + os.getenv -> 2 env-read hits
    assert len(result.env_reads_in_closure) >= 2


# ---------------------------------------------------------------------------
# Per-file scanner public surface (granular tests)
# ---------------------------------------------------------------------------


def test_inner_file_scan_result_fields_locked():
    """InnerFileScanResult must expose: network, phoenix1,
    cross_stage, env_reads, subprocess, sqlite (cross_stage added
    per operator patch on Phase 3)."""
    assert ca.InnerFileScanResult._fields == (
        "network",
        "phoenix1",
        "cross_stage",
        "env_reads",
        "subprocess",
        "sqlite",
    )


def test_outer_file_scan_result_fields_locked():
    assert ca.OuterFileScanResult._fields == (
        "network",
        "phoenix1",
        "cross_stage",
    )


def test_scan_inner_file_returns_inner_file_scan_result(tmp_path: Path):
    f = tmp_path / "foo.py"
    f.write_text("import requests\n", encoding="utf-8")
    r = ca.scan_inner_file(f)
    assert isinstance(r, ca.InnerFileScanResult)
    assert len(r.network) == 1


def test_scan_inner_file_records_cross_stage_locally(tmp_path: Path):
    """Per-file inner scanner returns cross-stage hits directly
    (not just via audit_codebase aggregation)."""
    f = tmp_path / "foo.py"
    f.write_text("from PHX2.stage19 import x\n", encoding="utf-8")
    r = ca.scan_inner_file(f)
    assert len(r.cross_stage) == 1
    assert r.cross_stage[0].module == "PHX2.stage19"
    assert r.cross_stage[0].reason == "cross_stage"


def test_scan_outer_file_returns_outer_file_scan_result(tmp_path: Path):
    f = tmp_path / "foo.py"
    f.write_text("from PHX2.stage17 import x\n", encoding="utf-8")
    r = ca.scan_outer_file(f)
    assert isinstance(r, ca.OuterFileScanResult)
    assert len(r.cross_stage) == 1


def test_scan_tokens_in_file_returns_tuple_pair(tmp_path: Path):
    f = tmp_path / "foo.py"
    f.write_text(
        "safe_for_live_dispatch = True\napi_key = 'x'\n",
        encoding="utf-8",
    )
    blocking, warning = ca.scan_tokens_in_file(f)
    assert len(blocking) == 1
    assert len(warning) == 1


def test_scan_inner_file_handles_syntax_error_gracefully(tmp_path: Path):
    """A file with broken syntax must not raise; the scanner returns
    an empty InnerFileScanResult."""
    f = tmp_path / "broken.py"
    f.write_text("def(:\n    pass\n", encoding="utf-8")
    r = ca.scan_inner_file(f)
    assert r.network == ()
    assert r.phoenix1 == ()


# ---------------------------------------------------------------------------
# AST self-audit of codebase_auditor.py
# ---------------------------------------------------------------------------


_FORBIDDEN_NETWORK = frozenset({
    "requests", "httpx", "aiohttp", "urllib3", "websockets",
    "grpc", "grpclib",
    "discord", "telegram", "telethon", "pyrogram",
})

_FORBIDDEN_INNER_ONLY = frozenset({
    "dotenv", "python_dotenv",
    "sqlite3", "aiosqlite",
    "subprocess",
    "git", "pygit2", "dulwich",
})

_FORBIDDEN_PHOENIX1 = frozenset({"phoenix1", "Phoenix1", "phx1"})


def _matches_any_prefix(name: str, blacklist: frozenset[str]) -> bool:
    if name in blacklist:
        return True
    for b in blacklist:
        if name.startswith(b + "."):
            return True
    return False


def _collect_imports(tree: ast.AST):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is not None:
                out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
    return out


def test_codebase_auditor_has_no_forbidden_network_imports():
    tree = ast.parse(Path(ca.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        assert not _matches_any_prefix(name, _FORBIDDEN_NETWORK), (
            f"codebase_auditor.py imports forbidden network module "
            f"{name!r} at line {lineno}"
        )


def test_codebase_auditor_has_no_forbidden_inner_only_imports():
    tree = ast.parse(Path(ca.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        assert not _matches_any_prefix(name, _FORBIDDEN_INNER_ONLY), (
            f"codebase_auditor.py imports forbidden inner-only "
            f"module {name!r} at line {lineno}"
        )


def test_codebase_auditor_has_no_phoenix1_imports():
    tree = ast.parse(Path(ca.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        assert not _matches_any_prefix(name, _FORBIDDEN_PHOENIX1), (
            f"codebase_auditor.py imports Phoenix1 module "
            f"{name!r} at line {lineno}"
        )


def test_codebase_auditor_does_not_import_phx2_stage20_outside_closure():
    tree = ast.parse(Path(ca.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        if name.startswith("PHX2.stage20") and not name.startswith(
            "PHX2.stage20.closure"
        ):
            pytest.fail(
                f"codebase_auditor.py imports {name!r} at line {lineno}"
            )


def test_codebase_auditor_has_no_env_reads():
    tree = ast.parse(Path(ca.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            value = node.value
            if (
                isinstance(value, ast.Name)
                and value.id == "os"
                and node.attr == "environ"
            ):
                pytest.fail(
                    f"codebase_auditor.py reads os.environ at line "
                    f"{node.lineno}"
                )
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr == "getenv"
                ):
                    pytest.fail(
                        f"codebase_auditor.py calls os.getenv at line "
                        f"{node.lineno}"
                    )


def test_codebase_auditor_does_not_import_subprocess_or_sqlite_or_git():
    """codebase_auditor must scan for these modules, but must NOT
    import them itself."""
    tree = ast.parse(Path(ca.__file__).read_text(encoding="utf-8"))
    forbidden = frozenset({
        "subprocess", "sqlite3", "aiosqlite",
        "git", "pygit2", "dulwich",
        "dotenv", "python_dotenv",
    })
    for name, lineno in _collect_imports(tree):
        if name in forbidden or any(
            name.startswith(b + ".") for b in forbidden
        ):
            pytest.fail(
                f"codebase_auditor.py imports {name!r} at line "
                f"{lineno}; auditor must not import what it audits"
            )
