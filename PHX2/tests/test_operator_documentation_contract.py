"""Operator documentation may not describe a noncanonical armed send path.

``AE-7`` README_DOCUMENTS_A_NONCANONICAL_FREE_TIER_SEND_PATH (2026-07-20, LOW).

Section D of the free-tier README documented a complete, copy-pasteable armed
send command:

    --run --enable-private-discord --ack-live-free-tier
    --i-understand-this-can-send --confirm-token $tok --require-baseline <...>

with **no** ``--provider-mode paid_primary``, **no**
``--require-production-grpc``, **no** ``--cursor-state-dir`` and **no**
``--ledger-path`` -- so it defaulted to ``free_tier`` provider mode and the
free-tier ledger.  Sections A2 and A3 pointed at it ("arm flags per section D"),
making it the documented way to arm any run shape in the file.

This is not a reconnect bypass by itself: ``--require-production-grpc`` is what
fails a run closed, and a command that never passes it simply never reaches the
gRPC contract.  The damage is quieter.  An operator following section D arms a
run that writes send history into the *free-tier* ledger while the three armed
launchers write into the *paid-primary* ledger, so dedupe and baseline history
split across two files that each believe they are authoritative -- and the
``--require-baseline`` pin on the launchers can no longer describe the ledger
the operator actually sent through.

The contract asserted here: any documented command carrying arm-gate flags must
be the canonical paid-primary shape, and the private-live route must be the
three PowerShell launchers rather than a directly invoked Python session file.

Static text inspection only.  Nothing is executed, opened or sent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest

from PHX2.free_tier_producer.launcher_contract import (
    ARMED_LAUNCHERS,
    CANONICAL_CURSOR_STATE_DIR,
    CANONICAL_LEDGER_PATH,
    CANONICAL_PROVIDER_MODE,
    PAID_PRIMARY_RUNTIME_ROOT,
    TRACKED_PRODUCTION_MODULE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

TRACKED_README = REPO_ROOT / "PHX2" / "free_tier_producer" / "README_FREE_TIER.md"
EXTERNAL_FREE_TIER_README = Path(
    r"C:\Users\BalaC\phx2_live_free_tier\README_FREE_TIER.md")
EXTERNAL_PRODUCTION_README = Path(
    r"C:\Users\BalaC\phx2_production_private_live\README_PRODUCTION_LIVE.md")

#: Any of these inside a command block makes it an ARMED command: each is a
#: flag the session's arm gate requires before it will send.
ARM_MARKERS = (
    "--i-understand-this-can-send",
    "--confirm-token",
    "--enable-private-discord",
)

#: Paths that must never appear as a write target in operator documentation.
FROZEN_CEREMONY_LEDGER = r"C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl"
FROZEN_CEREMONY_ROOT = r"phx2_one_send_ceremony"
FREE_TIER_LEDGER_ROOT = r"phx2_live_free_tier"

#: Python session files an operator must never be told to invoke directly.
DIRECT_SESSION_FILES = ("production_live_session.py", "free_tier_session.py")


def _docs() -> Dict[str, Path]:
    found = {"tracked": TRACKED_README}
    if EXTERNAL_FREE_TIER_README.exists():
        found["external_free_tier"] = EXTERNAL_FREE_TIER_README
    if EXTERNAL_PRODUCTION_README.exists():
        found["external_production"] = EXTERNAL_PRODUCTION_README
    return found


DOCS = _docs()


def _command_blocks(path: Path) -> List[str]:
    """Every fenced code block, joined. Prose commentary is deliberately out."""

    blocks: List[str] = []
    current: List[str] = []
    inside = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
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


def _armed_blocks(path: Path) -> List[str]:
    return [block for block in _command_blocks(path)
            if any(marker in block for marker in ARM_MARKERS)]


@pytest.mark.parametrize("name", sorted(DOCS))
def test_every_armed_command_block_is_canonical(name):
    """An armed command must carry the whole production gRPC shape."""

    path = DOCS[name]
    problems: List[str] = []
    for index, block in enumerate(_armed_blocks(path)):
        missing = []
        if TRACKED_PRODUCTION_MODULE not in block:
            missing.append("tracked module")
        if f"--provider-mode {CANONICAL_PROVIDER_MODE}" not in block:
            missing.append("--provider-mode paid_primary")
        if "--require-production-grpc" not in block:
            missing.append("--require-production-grpc")
        if CANONICAL_LEDGER_PATH not in block:
            missing.append("canonical paid-primary ledger")
        if CANONICAL_CURSOR_STATE_DIR not in block:
            missing.append("canonical --cursor-state-dir")
        if missing:
            problems.append(f"{path.name} armed block #{index}: missing "
                            + ", ".join(missing))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("name", sorted(DOCS))
def test_no_armed_command_block_targets_a_noncanonical_ledger(name):
    """Arming must never write send history outside the paid-primary ledger."""

    path = DOCS[name]
    problems: List[str] = []
    for index, block in enumerate(_armed_blocks(path)):
        for bad, label in ((FROZEN_CEREMONY_ROOT, "frozen ceremony ledger"),
                           (FREE_TIER_LEDGER_ROOT, "free-tier ledger root")):
            if bad in block:
                problems.append(
                    f"{path.name} armed block #{index} targets {label}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("name", sorted(DOCS))
def test_no_command_block_invokes_a_python_session_file_directly(name):
    """The private-live route is the launchers, never a bare session file."""

    path = DOCS[name]
    problems: List[str] = []
    for index, block in enumerate(_command_blocks(path)):
        for session_file in DIRECT_SESSION_FILES:
            for invocation in (f"$PY {session_file}", f"python {session_file}",
                               f"$PY -u {session_file}"):
                if invocation in block:
                    problems.append(
                        f"{path.name} block #{index} runs {session_file}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("name", sorted(DOCS))
def test_frozen_ceremony_ledger_is_never_a_documented_target(name):
    """The frozen 16-line ceremony ledger is history, not a runtime path."""

    path = DOCS[name]
    problems = [
        f"{path.name} block #{index} names the frozen ceremony ledger"
        for index, block in enumerate(_command_blocks(path))
        if FROZEN_CEREMONY_LEDGER in block or FROZEN_CEREMONY_ROOT in block]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("name", sorted(DOCS))
def test_documentation_names_the_canonical_armed_launchers(name):
    """Every operator document must route arming to the same three scripts."""

    text = DOCS[name].read_text(encoding="utf-8", errors="replace")
    missing = [launcher for launcher in ARMED_LAUNCHERS
               if launcher not in text]
    assert not missing, f"{DOCS[name].name} does not name {missing}"


@pytest.mark.parametrize("name", sorted(DOCS))
def test_documentation_states_the_canonical_runtime_root(name):
    """Durable state, ledger and run output must be named unambiguously."""

    text = DOCS[name].read_text(encoding="utf-8", errors="replace")
    assert PAID_PRIMARY_RUNTIME_ROOT in text, (
        f"{DOCS[name].name} never names the paid-primary runtime root")
    assert CANONICAL_LEDGER_PATH in text, (
        f"{DOCS[name].name} never names the canonical ledger")


@pytest.mark.parametrize("name", sorted(DOCS))
def test_documentation_separates_observation_from_production(name):
    """Free-tier observation may not be presented as the production path."""

    text = DOCS[name].read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    # A document that mentions free-tier running at all must say plainly that
    # it is not the production gRPC route.
    if "free_tier" in lowered or "free-tier" in lowered:
        assert ("not the production" in lowered
                or "no-send" in lowered
                or "observation" in lowered), (
            f"{DOCS[name].name} does not separate free-tier observation "
            "from the production gRPC path")


def test_tracked_readme_cross_references_do_not_point_at_an_armed_section():
    """A2/A3 said 'arm flags per section D', which is what made D reachable."""

    text = TRACKED_README.read_text(encoding="utf-8", errors="replace")
    # Headings are the routing surface: they are what an operator scans to find
    # "how do I arm this shape". Body prose may quote the retired wording when
    # explaining why it was retired.
    offenders = [line.strip() for line in text.splitlines()
                 if line.lstrip().startswith("#")
                 and "arm flags per" in line.lower()]
    assert not offenders, (
        "tracked README still routes run shapes to an inline arm recipe: "
        + " | ".join(offenders))
