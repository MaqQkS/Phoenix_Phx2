"""Repository entrypoint documentation may not present a noncanonical armed path.

``M-3`` STALE_RUNBOOK_EXPOSES_NONCANONICAL_ARMED_COMMAND (2026-07-20 residual
re-audit, MEDIUM).

``PHX2/entrypoint/BUILD_23_MAIN_ENTRYPOINT_RUNBOOK.md`` presented, under a
heading literally titled *"1. Command surface"*, an armed private-live command

    python main.py --mode private-supervised --live --post-send stop \\
        --require-baseline <sha256>:<size_bytes>:<line_count>

with no deprecation banner, no mention of the three canonical launchers,
``paid_primary`` or ``--require-production-grpc``.  It is a competing armed
command surface in active repository documentation, outside the three-README
scope that ``test_operator_documentation_contract.py`` enforces.

The contract asserted here covers every tracked ``*.md`` / ``*.txt`` under the
repository: an armed or ``--live`` private-live command block must either be the
full canonical production-gRPC shape, or live in a file that is clearly,
prominently deprecated.  Static text inspection only; nothing is executed.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_PROVIDER_MODE,
    TRACKED_PRODUCTION_MODULE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD23_RUNBOOK = REPO_ROOT / "PHX2" / "entrypoint" / "BUILD_23_MAIN_ENTRYPOINT_RUNBOOK.md"

#: Substrings that make a fenced command block an ARMED or LIVE private-live
#: command. Any one of these in a code block flags it for the contract below.
#: (Non-sending verbs like ``--preflight-only`` / ``--dry-run`` are deliberately
#: excluded -- they neither arm nor send.)
ARMED_COMMAND_MARKERS = (
    "--i-understand-this-can-send",
    "--confirm-token",
    "--enable-private-discord",
    "--mode private-supervised --live",
)

#: A file is "clearly deprecated" only when one of these appears in its opening
#: lines -- a banner an operator cannot miss.
DEPRECATION_BANNER_WORDS = (
    "deprecated", "superseded", "do not run", "obsolete", "historical",
    "decommission", "retired", "not a supported", "no longer",
)

CANONICAL_LAUNCHERS = (
    "launch_pressure_24h_01.ps1",
    "launch_soak_02h_01.ps1",
    "launch_window_04.ps1",
)


def _iter_repo_docs() -> List[Path]:
    docs: List[Path] = []
    for pattern in ("**/*.md", "**/*.txt"):
        for path in REPO_ROOT.glob(pattern):
            parts = set(path.parts)
            if ".venv" in parts or ".git" in parts or "__pycache__" in parts:
                continue
            docs.append(path)
    return sorted(docs)


def _command_blocks(text: str) -> List[str]:
    blocks: List[str] = []
    current: List[str] = []
    inside = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if inside:
                blocks.append("\n".join(current))
                current = []
            inside = not inside
            continue
        if inside:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _has_prominent_deprecation_banner(text: str) -> bool:
    head = "\n".join(text.splitlines()[:20]).lower()
    return any(word in head for word in DEPRECATION_BANNER_WORDS)


def _armed_blocks(text: str) -> List[str]:
    return [block for block in _command_blocks(text)
            if any(marker in block for marker in ARMED_COMMAND_MARKERS)]


def _is_canonical_armed_block(block: str) -> bool:
    """A canonical armed block carries the tracked module, paid_primary and the
    production-gRPC contract flag -- the shape the three launchers pass."""
    return (TRACKED_PRODUCTION_MODULE in block
            and f"--provider-mode {CANONICAL_PROVIDER_MODE}" in block
            and "--require-production-grpc" in block)


def _unmarked_noncanonical_armed_blocks(path: Path) -> List[int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if _has_prominent_deprecation_banner(text):
        return []
    return [index for index, block in enumerate(_armed_blocks(text))
            if not _is_canonical_armed_block(block)]


# ---------------------------------------------------------------------------
# BUILD_23 runbook: the named finding.
# ---------------------------------------------------------------------------

def test_build23_runbook_exists():
    assert BUILD23_RUNBOOK.is_file()


def test_build23_runbook_carries_a_prominent_deprecation_banner():
    text = BUILD23_RUNBOOK.read_text(encoding="utf-8")
    assert _has_prominent_deprecation_banner(text), (
        "BUILD_23 runbook presents an entrypoint procedure with no prominent "
        "deprecation/historical banner in its opening lines")


def test_build23_runbook_has_no_unmarked_noncanonical_armed_command():
    offenders = _unmarked_noncanonical_armed_blocks(BUILD23_RUNBOOK)
    assert not offenders, (
        f"{BUILD23_RUNBOOK.name} presents unmarked noncanonical armed command "
        f"block(s) at index {offenders}")


def test_build23_runbook_routes_to_the_canonical_launchers():
    """The runbook must direct the operator to the three canonical launchers,
    not to a bare ``main.py`` armed command."""
    text = BUILD23_RUNBOOK.read_text(encoding="utf-8")
    missing = [name for name in CANONICAL_LAUNCHERS if name not in text]
    assert not missing, (
        f"BUILD_23 runbook does not name the canonical launchers: {missing}")


# ---------------------------------------------------------------------------
# Repository-wide sweep: no tracked doc may present an unmarked, noncanonical
# armed command block.
# ---------------------------------------------------------------------------

def test_no_repo_doc_presents_an_unmarked_noncanonical_armed_command():
    offenders: List[str] = []
    for path in _iter_repo_docs():
        for index in _unmarked_noncanonical_armed_blocks(path):
            offenders.append(f"{path.relative_to(REPO_ROOT)} armed block #{index}")
    assert not offenders, (
        "unmarked noncanonical armed private-live command blocks in tracked "
        "docs:\n" + "\n".join(offenders))


def test_no_repo_doc_invokes_the_out_of_repo_session_file_directly():
    """No tracked doc may present a direct ``production_live_session.py`` armed
    invocation as a runnable command."""
    offenders: List[str] = []
    for path in _iter_repo_docs():
        text = path.read_text(encoding="utf-8", errors="replace")
        if _has_prominent_deprecation_banner(text):
            continue
        for index, block in enumerate(_command_blocks(text)):
            for invocation in ("python production_live_session.py",
                               "$PY production_live_session.py",
                               "$PY -u production_live_session.py"):
                if invocation in block:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)} block #{index}")
    assert not offenders, (
        "direct out-of-repo session invocation in tracked docs:\n"
        + "\n".join(offenders))
