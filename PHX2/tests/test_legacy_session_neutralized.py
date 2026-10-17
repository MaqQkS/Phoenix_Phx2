"""The out-of-repo legacy production session must be inert, not merely unreachable.

``AE-1`` LEGACY_PRODUCTION_SESSION_REMAINS_SEND_CAPABLE (2026-07-20 re-audit, LOW).

``C:\\Users\\BalaC\\phx2_production_private_live\\production_live_session.py``
was a complete, independently executable, send-capable production
implementation: Helius log-subscription discovery, the Build 29/30 compose-send
lineage, the Axiom fee gate, a real private Discord transport seam and a durable
ledger writer.  It imports nothing from ``PHX2.free_tier_producer``, so it
reaches no durable stream cursor, no reconnect-recovery contract and no
``--require-production-grpc`` gate.

After commit ``7e96c14`` it was unreachable from every armed launcher and would
fail closed on a stale ``--expected-head`` pin.  That is a *configuration*
barrier around a live implementation, not the absence of one: refresh the pin,
or invoke the file directly the way this repository's own external README still
documented, and the whole bypassed path executes.

Its sibling ``phx2_live_free_tier/free_tier_session.py`` was already reduced to
a fail-closed shim by the same commit.  This file pins the equivalent contract
for the production session, and holds the free-tier shim to it too so the two
cannot drift.

Every assertion here is static source inspection plus one local, network-free
subprocess.  Nothing opens a socket, reads an environment file, touches a
credential, mutates a ledger or sends anything.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

PRODUCTION_LIVE_ROOT = Path(r"C:\Users\BalaC\phx2_production_private_live")
FREE_TIER_ROOT = Path(r"C:\Users\BalaC\phx2_live_free_tier")

LEGACY_SESSION = PRODUCTION_LIVE_ROOT / "production_live_session.py"
LEGACY_FREE_TIER_SESSION = FREE_TIER_ROOT / "free_tier_session.py"

TRACKED_MODULE = "PHX2.free_tier_producer.free_tier_session"

ARMED_LAUNCHERS = (
    "launch_pressure_24h_01.ps1",
    "launch_soak_02h_01.ps1",
    "launch_window_04.ps1",
)

#: Code-level needles proving a live implementation is still present. Chosen so
#: that safe prose in a shim's own docstring cannot trip them: each is an
#: identifier or dotted call that only appears in executing code.
FORBIDDEN_IMPLEMENTATION_TOKENS = {
    # discovery
    "logsSubscribe": "LEGACY_WEBSOCKET_DISCOVERY",
    "SubscribeRequest": "SUBSCRIPTION_CONSTRUCTION",
    "websockets.": "WEBSOCKET_CLIENT",
    # transport / outbound
    "requests.post": "OUTBOUND_HTTP",
    "urllib.request": "OUTBOUND_HTTP",
    "http.client": "OUTBOUND_HTTP",
    "httpx.": "OUTBOUND_HTTP",
    "socket.socket": "RAW_SOCKET",
    "Stage28_4": "PRIVATE_TRANSPORT_SEAM",
    "Stage28_9": "PRIVATE_TRANSPORT_SEAM",
    "AxiomFeeAppendingTransport": "PRIVATE_TRANSPORT_SEAM",
    # ledger mutation
    "ping_dedupe": "LEDGER_MUTATION",
    "DurableLedger": "LEDGER_MUTATION",
    "reserve_ping": "LEDGER_MUTATION",
    # wallet / signing
    "Keypair": "WALLET_MATERIAL",
    "sign_transaction": "WALLET_MATERIAL",
    "send_transaction": "WALLET_MATERIAL",
    # environment / credential loading
    "os.environ": "ENVIRONMENT_READ",
    "getenv": "ENVIRONMENT_READ",
    "dotenv": "ENVIRONMENT_READ",
    "load_env": "ENVIRONMENT_READ",
    # the legacy runtime it used to orchestrate
    "build29_cap1": "LEGACY_RUNTIME_IMPORT",
    "build30_session": "LEGACY_RUNTIME_IMPORT",
    "production_live_runner": "LEGACY_RUNTIME_IMPORT",
    "production_live_axiom": "LEGACY_RUNTIME_IMPORT",
    "production_live_artifacts": "LEGACY_RUNTIME_IMPORT",
    "importlib": "DYNAMIC_LEGACY_IMPORT",
    "__import__": "DYNAMIC_LEGACY_IMPORT",
    # the arm gate itself must not be reachable or advertised here
    "--i-understand-this-can-send": "ARM_GATE_PRESENT",
    "--confirm-token": "ARM_GATE_PRESENT",
    "--enable-private-discord": "ARM_GATE_PRESENT",
    "argparse": "EXECUTABLE_CLI",
}

#: A shim may be at most this large. The pre-fix file was 44,946 bytes; the
#: already-neutralised free-tier sibling is 3,546.
MAX_SHIM_BYTES = 8_192

requires_legacy_session = pytest.mark.skipif(
    not LEGACY_SESSION.exists(),
    reason="out-of-repo production session absent on this machine")
requires_free_tier_session = pytest.mark.skipif(
    not LEGACY_FREE_TIER_SESSION.exists(),
    reason="out-of-repo free-tier session absent on this machine")


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _executable_source(path: Path) -> str:
    """The module with every docstring and comment removed.

    A shim's prose must stay free to say what the file no longer does -- naming
    the ledger it does not touch, or the runtime it no longer imports -- without
    that description reading as the thing itself.  Only executing code and the
    string literals it actually emits are scanned.
    """

    tree = ast.parse(_source(path))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _powershell_statements(path: Path) -> str:
    """Launcher text with ``#`` comment lines removed.

    Every armed launcher carries a historical banner naming the legacy session
    it used to invoke.  Recording that history is required; invoking it is the
    defect, so only statement lines are inspected.
    """

    return "\n".join(
        line for line in _source(path).splitlines()
        if not line.lstrip().startswith("#"))


# ---------------------------------------------------------------------------
# static inertness
# ---------------------------------------------------------------------------

@requires_legacy_session
def test_legacy_session_is_a_small_shim():
    assert LEGACY_SESSION.stat().st_size <= MAX_SHIM_BYTES, (
        "production_live_session.py is still a full implementation "
        f"({LEGACY_SESSION.stat().st_size} bytes)")


@requires_legacy_session
def test_legacy_session_contains_no_live_implementation():
    source = _executable_source(LEGACY_SESSION)
    found = sorted({
        f"{token} -> {reason}"
        for token, reason in FORBIDDEN_IMPLEMENTATION_TOKENS.items()
        if token in source})
    assert not found, (
        "production_live_session.py still carries live implementation: "
        + "; ".join(found))


@requires_legacy_session
def test_legacy_session_names_the_canonical_path():
    """The operator must be told where to go, not merely refused."""

    source = _source(LEGACY_SESSION)
    assert TRACKED_MODULE in source
    for launcher in ARMED_LAUNCHERS:
        assert launcher in source, f"shim does not name {launcher}"


@requires_legacy_session
def test_legacy_session_does_not_point_into_a_forbidden_write_root():
    """A shim that names a refused path is still misdirecting the operator."""

    source = _executable_source(LEGACY_SESSION)
    assert r"phx2_one_send_ceremony" not in source
    # Naming its own directory as a *state* or *output* target is the error;
    # naming the launchers that live there is required.
    for bad in (r"phx2_production_private_live\state",
                r"phx2_production_private_live\out"):
        assert bad not in source, f"shim directs durable state to {bad}"


# ---------------------------------------------------------------------------
# executable inertness
# ---------------------------------------------------------------------------

@requires_legacy_session
def test_legacy_session_refuses_to_execute():
    """Running it exits nonzero with a clear message and does nothing else."""

    completed = subprocess.run(
        [sys.executable, "-B", str(LEGACY_SESSION)],
        capture_output=True, text=True, timeout=60,
        cwd=str(PRODUCTION_LIVE_ROOT))

    assert completed.returncode != 0, "legacy session exited 0 (it ran)"
    combined = (completed.stdout or "") + (completed.stderr or "")
    assert TRACKED_MODULE in combined
    assert any(name in combined for name in ARMED_LAUNCHERS)


@requires_legacy_session
@pytest.mark.parametrize("argv", [
    ["--selftest"], ["--check-wiring"], ["--preflight"], ["--run"],
])
def test_legacy_session_refuses_every_historical_mode(argv):
    """No surviving mode may execute, including the old read-only ones."""

    completed = subprocess.run(
        [sys.executable, "-B", str(LEGACY_SESSION), *argv],
        capture_output=True, text=True, timeout=60,
        cwd=str(PRODUCTION_LIVE_ROOT))

    assert completed.returncode != 0, f"legacy session ran mode {argv}"


@requires_legacy_session
def test_legacy_session_cannot_be_imported():
    """Importing it must fail loudly, so nothing can build discovery from it."""

    code = (
        "import sys; sys.path.insert(0, r'%s');\n"
        "import production_live_session\n" % PRODUCTION_LIVE_ROOT)
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True, text=True, timeout=60)

    assert completed.returncode != 0, "legacy session imported cleanly"


# ---------------------------------------------------------------------------
# the already-neutralised sibling must not regress
# ---------------------------------------------------------------------------

@requires_free_tier_session
def test_free_tier_shim_stays_inert():
    source = _executable_source(LEGACY_FREE_TIER_SESSION)
    assert LEGACY_FREE_TIER_SESSION.stat().st_size <= MAX_SHIM_BYTES
    found = sorted({
        token for token in FORBIDDEN_IMPLEMENTATION_TOKENS
        if token in source})
    assert not found, f"free-tier shim regained implementation: {found}"
    assert TRACKED_MODULE in _source(LEGACY_FREE_TIER_SESSION)


@requires_free_tier_session
def test_free_tier_shim_does_not_point_into_a_forbidden_write_root():
    """The shim's printed example must be runnable, not refused at startup."""

    source = _executable_source(LEGACY_FREE_TIER_SESSION)
    for bad in (r"phx2_production_private_live\state",
                r"phx2_production_private_live\out",
                r"phx2_one_send_ceremony"):
        assert bad not in source, f"free-tier shim directs the operator to {bad}"


# ---------------------------------------------------------------------------
# disabled backups stay unreachable
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PRODUCTION_LIVE_ROOT.exists(),
                    reason="production-live root absent on this machine")
def test_disabled_backups_are_not_reachable_from_any_armed_launcher():
    """A retained ``.bak.disabled`` file may exist, but nothing may invoke it."""

    disabled = sorted(PRODUCTION_LIVE_ROOT.glob("*.disabled"))
    for path in disabled:
        # The extension keeps it from running; the banner keeps a reader from
        # mistaking a retained armed command for a live one.
        assert path.suffix == ".disabled", path.name
        banner = "\n".join(_source(path).splitlines()[:12]).upper()
        assert "DO NOT RUN" in banner or "DISABLED" in banner, (
            f"{path.name} carries no disabled banner")

    names = {path.name for path in disabled}
    for launcher in ARMED_LAUNCHERS:
        launcher_path = PRODUCTION_LIVE_ROOT / launcher
        if not launcher_path.exists():
            continue
        statements = _powershell_statements(launcher_path)
        for name in names:
            assert name not in statements, (
                f"{launcher} references disabled {name}")
        assert "production_live_session" not in statements, (
            f"{launcher} still invokes the legacy session")
        assert TRACKED_MODULE in statements, (
            f"{launcher} does not execute the tracked module")
