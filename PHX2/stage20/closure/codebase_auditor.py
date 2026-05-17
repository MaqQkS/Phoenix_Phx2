"""Stage 20.4 codebase auditor.

Two-layer AST-level scan over the PHX2/stage20/ source tree plus
a separate regex-based forbidden / warning token scan.

Scopes (locked):

  * INNER  -- PHX2/stage20/closure/  (excludes __pycache__/)
  * OUTER  -- PHX2/stage20/          (excludes /closure/ AND __pycache__/)

Inner-scope rules:

  * Forbidden import modules (E2037, except Phoenix1 -> E2038):
    network/dispatch clients, dotenv, sqlite, subprocess, git
    tools, Phoenix1.
  * Cross-stage prefixes ``PHX2.stage17 / .stage18 / .stage19``
    -> E2039 (closure code must never reach into prior pipeline
    stages directly; per operator patch, this is enforced in
    the inner scope, not just outer).
  * Forbidden env reads: ``os.environ`` access and
    ``os.getenv(...)`` calls. Recorded in
    ``env_reads_in_closure`` (reason="env_read"); treated as
    E2037 by the checklist (per C.5: "Tied to error code E2037
    in checklist (env reads are a network/secret-adjacent class
    for our purposes)").

Outer-scope rules:

  * Forbidden import modules: network/dispatch clients, Phoenix1.
    (Outer scope does NOT check env reads / subprocess /
    sqlite / dotenv / git -- those are inner-only.)
  * Cross-stage prefixes ``PHX2.stage17 / .stage18 / .stage19``
    -> E2039.

Token scan (separate from import scan):

  * Scope: PHX2/stage20/*.py recursively, EXCLUDING
    ``/templates/`` and ``/__pycache__/``.
  * BLOCKING patterns -> E2040 (TokenHit severity="error").
  * WARNING patterns  -> W2025 (TokenHit severity="warning";
    informational, does not flip ``passed`` to False).

Public entry point:

  ``audit_codebase(repo_root, *, inner_root=None, outer_root=None)``

Returns a ``CodebaseAuditResult`` (NamedTuple). The ``passed``
field is True iff every error-class bucket is empty
(``warning_token_hits`` does not affect ``passed``).

Bucket mapping for the locked ``CodebaseAuditResult`` fields:

  - ``forbidden_network_imports``  -- network/dispatch clients,
                                      dotenv, git tools. Reason
                                      field distinguishes the
                                      subcategory.
  - ``forbidden_phoenix1_imports`` -- phoenix1 / Phoenix1 / phx1.
  - ``cross_stage_violations``     -- PHX2.stage17/18/19
                                      (BOTH inner closure scope AND
                                      outer stage20 scope; closure
                                      code must not reach into prior
                                      pipeline stages either).
  - ``env_reads_in_closure``       -- os.environ / os.getenv
                                      (inner scope only).
  - ``subprocess_uses_in_closure`` -- subprocess (inner scope
                                      only).
  - ``sqlite_imports_in_closure``  -- sqlite3 / aiosqlite (inner
                                      scope only).
  - ``blocking_token_hits``        -- BLOCKING_TOKEN_REGEXES hits.
  - ``warning_token_hits``         -- WARNING_TOKEN_REGEXES hits.

What Stage 20.4 codebase_auditor will NOT do:

  * Does NOT scan the full repository (only PHX2/stage20/).
  * Does NOT invoke git.
  * Does NOT invoke subprocess.
  * Does NOT read environment variables.
  * Does NOT cross the closure -> wider stage20 import boundary
    in its own production code (verified by AST self-audit in
    test_codebase_auditor.py and the test_no_*.py suite).

Phoenix1 departure note: this module imports no Phoenix1 code
and references Phoenix1 only via the forbidden-module list
defined in PHX2.stage20.closure.constants.

Known limitations (v0):

  * Files with Python syntax errors are silently skipped by the
    import scanner. They are still token-scanned.
  * Module-matching is case-sensitive (matches the locked spec).
    Phoenix1 prefixes ``phoenix1`` / ``Phoenix1`` / ``phx1`` are
    all listed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple

from PHX2.stage20.closure.constants import (
    BLOCKING_TOKEN_REGEXES,
    FORBIDDEN_CROSS_STAGE_PREFIXES,
    FORBIDDEN_NETWORK_MODULES,
    FORBIDDEN_PHOENIX1_MODULES,
    WARNING_TOKEN_REGEXES,
)
from PHX2.stage20.closure.models import (
    CodebaseAuditResult,
    ImportHit,
    TokenHit,
)


# ---------------------------------------------------------------------------
# Path-substring exclusions (normalized to forward slashes)
# ---------------------------------------------------------------------------


_PYCACHE_EXCLUSION = "/__pycache__/"
_CLOSURE_EXCLUSION = "/closure/"
_TEMPLATES_EXCLUSION = "/templates/"


# ---------------------------------------------------------------------------
# Reason-field strings (carried on ImportHit.reason for visibility)
# ---------------------------------------------------------------------------


_REASON_NETWORK_CLIENT = "network_client"
_REASON_GRPC = "grpc"
_REASON_DISPATCH_CLIENT = "dispatch_client"
_REASON_DOTENV = "dotenv"
_REASON_SQLITE = "sqlite"
_REASON_SUBPROCESS = "subprocess"
_REASON_GIT = "git"
_REASON_PHOENIX1 = "phoenix1"
_REASON_CROSS_STAGE = "cross_stage"
_REASON_ENV_READ = "env_read"


# Subcategory module sets (driving the reason field per match).
_NETWORK_CLIENT_MODULES: tuple[str, ...] = (
    "requests", "httpx", "aiohttp", "urllib3", "websockets",
)
_GRPC_MODULES: tuple[str, ...] = ("grpc", "grpclib")
_DISPATCH_CLIENT_MODULES: tuple[str, ...] = (
    "discord", "telegram", "telethon", "pyrogram",
)
_DOTENV_MODULES: tuple[str, ...] = ("dotenv", "python_dotenv")
_SQLITE_MODULES: tuple[str, ...] = ("sqlite3", "aiosqlite")
_GIT_MODULES: tuple[str, ...] = ("git", "pygit2", "dulwich")


# Compile token-scan regexes once.
_BLOCKING_PATTERNS = tuple(
    re.compile(p, re.MULTILINE) for p in BLOCKING_TOKEN_REGEXES
)
_WARNING_PATTERNS = tuple(
    re.compile(p, re.MULTILINE) for p in WARNING_TOKEN_REGEXES
)


# ---------------------------------------------------------------------------
# Per-file scan result shapes (public for granular tests)
# ---------------------------------------------------------------------------


class InnerFileScanResult(NamedTuple):
    """Per-file result of the inner-scope scan.

    ``cross_stage`` carries inner-scope ``PHX2.stage17 / .stage18 /
    .stage19`` hits (per the patched policy: inner scope also flags
    cross-stage). Top-level ``audit_codebase`` merges inner-scope
    cross-stage hits into the same ``cross_stage_violations`` bucket
    that the outer scope contributes to.
    """

    network: tuple
    phoenix1: tuple
    cross_stage: tuple
    env_reads: tuple
    subprocess: tuple
    sqlite: tuple


class OuterFileScanResult(NamedTuple):
    """Per-file result of the outer-scope scan."""

    network: tuple
    phoenix1: tuple
    cross_stage: tuple


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _normalize_path(p: Path) -> str:
    """Forward-slash normalized absolute path string (cross-platform)."""

    return str(p).replace("\\", "/")


def _walk_py(
    directory: Path,
    exclude_substrings: tuple[str, ...],
    out: list[Path],
) -> None:
    """Depth-first, alphabetically-sorted recursive walk for .py files.

    Each directory's children are iterated in ``sorted(... key=name)``
    order so the resulting file list is deterministic across runs and
    operating systems.
    """

    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        # Probe-string includes trailing slash for directories so a
        # substring like "/closure/" matches the directory but not a
        # file named "closure.py".
        norm = _normalize_path(entry) + ("/" if entry.is_dir() else "")
        if any(s in norm for s in exclude_substrings):
            continue
        if entry.is_dir():
            _walk_py(entry, exclude_substrings, out)
        elif entry.is_file() and entry.suffix == ".py":
            out.append(entry)


def _list_py_files(
    directory: Path,
    exclude_substrings: tuple[str, ...] = (),
) -> tuple[Path, ...]:
    """Return a deterministic tuple of .py files under ``directory``."""

    if not directory.exists() or not directory.is_dir():
        return ()
    result: list[Path] = []
    _walk_py(directory, exclude_substrings, result)
    return tuple(result)


def list_inner_scope_files(inner_root: Path) -> tuple[Path, ...]:
    """List .py files under inner_root, excluding __pycache__/."""

    return _list_py_files(
        inner_root,
        exclude_substrings=(_PYCACHE_EXCLUSION,),
    )


def list_outer_scope_files(outer_root: Path) -> tuple[Path, ...]:
    """List .py files under outer_root, excluding closure/ and __pycache__/."""

    return _list_py_files(
        outer_root,
        exclude_substrings=(_CLOSURE_EXCLUSION, _PYCACHE_EXCLUSION),
    )


def list_token_scan_files(scan_root: Path) -> tuple[Path, ...]:
    """List .py files under scan_root, excluding templates/ and __pycache__/."""

    return _list_py_files(
        scan_root,
        exclude_substrings=(_TEMPLATES_EXCLUSION, _PYCACHE_EXCLUSION),
    )


# ---------------------------------------------------------------------------
# Module-name matching
# ---------------------------------------------------------------------------


def _module_matches_any(
    module_name: str,
    prefixes: tuple[str, ...],
) -> bool:
    """Per the locked spec C.5 matching rule:

    Match by exact module name OR module name prefix followed by ``"."``
    (so ``"grpc"`` matches ``"grpc"`` and ``"grpc.aio"`` but not
    ``"grpcio_fake"``).
    """

    for prefix in prefixes:
        if module_name == prefix or module_name.startswith(prefix + "."):
            return True
    return False


def _categorize_inner_import(
    module_name: str,
) -> tuple[str, str] | None:
    """Return (bucket, reason) for an inner-scope import, or None.

    Bucket is one of ``"network" | "phoenix1" | "cross_stage" |
    "sqlite" | "subprocess"`` (env reads handled separately, not
    via this function). The dotenv / git / network-client /
    dispatch-client subcategories all land in the ``"network"``
    bucket per the locked CodebaseAuditResult field set.
    """

    # Phoenix1 first (case-sensitive list).
    if _module_matches_any(module_name, FORBIDDEN_PHOENIX1_MODULES):
        return ("phoenix1", _REASON_PHOENIX1)
    if _module_matches_any(module_name, _NETWORK_CLIENT_MODULES):
        return ("network", _REASON_NETWORK_CLIENT)
    if _module_matches_any(module_name, _GRPC_MODULES):
        return ("network", _REASON_GRPC)
    if _module_matches_any(module_name, _DISPATCH_CLIENT_MODULES):
        return ("network", _REASON_DISPATCH_CLIENT)
    if _module_matches_any(module_name, _DOTENV_MODULES):
        return ("network", _REASON_DOTENV)
    if _module_matches_any(module_name, _GIT_MODULES):
        return ("network", _REASON_GIT)
    if _module_matches_any(module_name, _SQLITE_MODULES):
        return ("sqlite", _REASON_SQLITE)
    if _module_matches_any(module_name, ("subprocess",)):
        return ("subprocess", _REASON_SUBPROCESS)
    # Per operator patch: closure inner scope must also hard-fail
    # on cross-stage imports (E2039), not just outer scope. AST
    # self-audit tests in test_codebase_auditor / test_input_loader
    # remain as defense-in-depth; this is the auditor enforcement.
    if _module_matches_any(module_name, FORBIDDEN_CROSS_STAGE_PREFIXES):
        return ("cross_stage", _REASON_CROSS_STAGE)
    return None


def _categorize_outer_import(
    module_name: str,
) -> tuple[str, str] | None:
    """Return (bucket, reason) for an outer-scope import, or None.

    Outer scope checks: network/dispatch clients + Phoenix1 +
    cross-stage. Does NOT check: dotenv, sqlite, subprocess, git,
    env reads.
    """

    if _module_matches_any(module_name, FORBIDDEN_PHOENIX1_MODULES):
        return ("phoenix1", _REASON_PHOENIX1)
    if _module_matches_any(module_name, _NETWORK_CLIENT_MODULES):
        return ("network", _REASON_NETWORK_CLIENT)
    if _module_matches_any(module_name, _GRPC_MODULES):
        return ("network", _REASON_GRPC)
    if _module_matches_any(module_name, _DISPATCH_CLIENT_MODULES):
        return ("network", _REASON_DISPATCH_CLIENT)
    if _module_matches_any(module_name, FORBIDDEN_CROSS_STAGE_PREFIXES):
        return ("cross_stage", _REASON_CROSS_STAGE)
    return None


# ---------------------------------------------------------------------------
# AST collectors
# ---------------------------------------------------------------------------


def _parse_file_safely(file_path: Path) -> tuple[str, ast.AST | None]:
    """Read source and parse AST. Returns (source, tree-or-None)."""

    source = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return source, None
    return source, tree


def _collect_import_module_names(tree: ast.AST) -> list[tuple[str, int]]:
    """Return (module_name, lineno) pairs from every Import / ImportFrom."""

    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # node.module is None for purely relative imports
            # like ``from . import x``; skip those.
            if node.module is not None:
                out.append((node.module, node.lineno))
    return out


def _collect_env_reads(tree: ast.AST) -> list[tuple[str, int]]:
    """Return (description, lineno) for os.environ access + os.getenv calls."""

    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        # os.environ attribute access
        if isinstance(node, ast.Attribute):
            value = node.value
            if (
                isinstance(value, ast.Name)
                and value.id == "os"
                and node.attr == "environ"
            ):
                out.append(("os.environ", node.lineno))
        # os.getenv(...) call
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
                and func.attr == "getenv"
            ):
                out.append(("os.getenv", node.lineno))
    return out


# ---------------------------------------------------------------------------
# Per-file scanners
# ---------------------------------------------------------------------------


def scan_inner_file(file_path: Path) -> InnerFileScanResult:
    """Scan one file for inner-scope violations."""

    _, tree = _parse_file_safely(file_path)
    if tree is None:
        return InnerFileScanResult((), (), (), (), (), ())

    file_str = _normalize_path(file_path)
    network: list[ImportHit] = []
    phoenix1: list[ImportHit] = []
    cross_stage: list[ImportHit] = []
    env_reads: list[ImportHit] = []
    subprocess_uses: list[ImportHit] = []
    sqlite_uses: list[ImportHit] = []

    for module_name, lineno in _collect_import_module_names(tree):
        cat = _categorize_inner_import(module_name)
        if cat is None:
            continue
        bucket, reason = cat
        hit = ImportHit(
            file=file_str,
            line=lineno,
            module=module_name,
            reason=reason,
        )
        if bucket == "network":
            network.append(hit)
        elif bucket == "phoenix1":
            phoenix1.append(hit)
        elif bucket == "cross_stage":
            cross_stage.append(hit)
        elif bucket == "subprocess":
            subprocess_uses.append(hit)
        elif bucket == "sqlite":
            sqlite_uses.append(hit)

    for desc, lineno in _collect_env_reads(tree):
        env_reads.append(ImportHit(
            file=file_str,
            line=lineno,
            module=desc,
            reason=_REASON_ENV_READ,
        ))

    return InnerFileScanResult(
        network=tuple(network),
        phoenix1=tuple(phoenix1),
        cross_stage=tuple(cross_stage),
        env_reads=tuple(env_reads),
        subprocess=tuple(subprocess_uses),
        sqlite=tuple(sqlite_uses),
    )


def scan_outer_file(file_path: Path) -> OuterFileScanResult:
    """Scan one file for outer-scope violations."""

    _, tree = _parse_file_safely(file_path)
    if tree is None:
        return OuterFileScanResult((), (), ())

    file_str = _normalize_path(file_path)
    network: list[ImportHit] = []
    phoenix1: list[ImportHit] = []
    cross_stage: list[ImportHit] = []

    for module_name, lineno in _collect_import_module_names(tree):
        cat = _categorize_outer_import(module_name)
        if cat is None:
            continue
        bucket, reason = cat
        hit = ImportHit(
            file=file_str,
            line=lineno,
            module=module_name,
            reason=reason,
        )
        if bucket == "network":
            network.append(hit)
        elif bucket == "phoenix1":
            phoenix1.append(hit)
        elif bucket == "cross_stage":
            cross_stage.append(hit)

    return OuterFileScanResult(
        network=tuple(network),
        phoenix1=tuple(phoenix1),
        cross_stage=tuple(cross_stage),
    )


# ---------------------------------------------------------------------------
# Token scanner
# ---------------------------------------------------------------------------


def _line_number_for_offset(source: str, offset: int) -> int:
    """1-based line number for a character offset into ``source``."""

    return source.count("\n", 0, offset) + 1


def _extract_token_context(source: str, match: re.Match) -> str:
    """Return up to 80 chars of surrounding context (the matched line)."""

    start, end = match.start(), match.end()
    line_start = source.rfind("\n", 0, start) + 1
    line_end = source.find("\n", end)
    if line_end == -1:
        line_end = len(source)
    line = source[line_start:line_end].rstrip("\r")
    if len(line) > 80:
        return line[:80]
    return line


def scan_tokens_in_file(
    file_path: Path,
) -> tuple[tuple[TokenHit, ...], tuple[TokenHit, ...]]:
    """Return (blocking_hits, warning_hits) for one file."""

    source = file_path.read_text(encoding="utf-8")
    file_str = _normalize_path(file_path)

    blocking: list[TokenHit] = []
    for pattern in _BLOCKING_PATTERNS:
        for match in pattern.finditer(source):
            blocking.append(TokenHit(
                file=file_str,
                line=_line_number_for_offset(source, match.start()),
                token=match.group(0),
                context=_extract_token_context(source, match),
                severity="error",
            ))

    warning: list[TokenHit] = []
    for pattern in _WARNING_PATTERNS:
        for match in pattern.finditer(source):
            warning.append(TokenHit(
                file=file_str,
                line=_line_number_for_offset(source, match.start()),
                token=match.group(0),
                context=_extract_token_context(source, match),
                severity="warning",
            ))

    return tuple(blocking), tuple(warning)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def audit_codebase(
    repo_root: Path,
    *,
    inner_root: Path | None = None,
    outer_root: Path | None = None,
) -> CodebaseAuditResult:
    """Run the Phase 3 codebase audit.

    Default roots (used when arguments are ``None``):
      * ``inner_root = repo_root / "PHX2" / "stage20" / "closure"``
      * ``outer_root = repo_root / "PHX2" / "stage20"``

    The override arguments exist so synthetic-tree tests can build
    a Stage 20-like structure under ``tmp_path`` and audit it.

    Token scan walks ``outer_root`` (covers both closure/ and the
    rest of stage20/) but excludes ``/templates/``.
    """

    if inner_root is None:
        inner_root = repo_root / "PHX2" / "stage20" / "closure"
    if outer_root is None:
        outer_root = repo_root / "PHX2" / "stage20"

    inner_files = list_inner_scope_files(inner_root)
    outer_files = list_outer_scope_files(outer_root)
    token_files = list_token_scan_files(outer_root)

    forbidden_network: list[ImportHit] = []
    forbidden_phoenix1: list[ImportHit] = []
    cross_stage: list[ImportHit] = []
    env_reads: list[ImportHit] = []
    subprocess_uses: list[ImportHit] = []
    sqlite_uses: list[ImportHit] = []
    blocking_tokens: list[TokenHit] = []
    warning_tokens: list[TokenHit] = []

    for fp in inner_files:
        r = scan_inner_file(fp)
        forbidden_network.extend(r.network)
        forbidden_phoenix1.extend(r.phoenix1)
        cross_stage.extend(r.cross_stage)
        env_reads.extend(r.env_reads)
        subprocess_uses.extend(r.subprocess)
        sqlite_uses.extend(r.sqlite)

    for fp in outer_files:
        r = scan_outer_file(fp)
        forbidden_network.extend(r.network)
        forbidden_phoenix1.extend(r.phoenix1)
        cross_stage.extend(r.cross_stage)

    for fp in token_files:
        block, warn = scan_tokens_in_file(fp)
        blocking_tokens.extend(block)
        warning_tokens.extend(warn)

    passed = (
        not forbidden_network
        and not forbidden_phoenix1
        and not cross_stage
        and not env_reads
        and not subprocess_uses
        and not sqlite_uses
        and not blocking_tokens
    )

    return CodebaseAuditResult(
        inner_files_scanned=tuple(_normalize_path(p) for p in inner_files),
        outer_files_scanned=tuple(_normalize_path(p) for p in outer_files),
        forbidden_network_imports=tuple(forbidden_network),
        forbidden_phoenix1_imports=tuple(forbidden_phoenix1),
        cross_stage_violations=tuple(cross_stage),
        env_reads_in_closure=tuple(env_reads),
        subprocess_uses_in_closure=tuple(subprocess_uses),
        sqlite_imports_in_closure=tuple(sqlite_uses),
        blocking_token_hits=tuple(blocking_tokens),
        warning_token_hits=tuple(warning_tokens),
        passed=passed,
    )


__all__ = [
    "InnerFileScanResult",
    "OuterFileScanResult",
    "audit_codebase",
    "list_inner_scope_files",
    "list_outer_scope_files",
    "list_token_scan_files",
    "scan_inner_file",
    "scan_outer_file",
    "scan_tokens_in_file",
]
