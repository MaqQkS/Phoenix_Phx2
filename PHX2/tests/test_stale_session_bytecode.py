"""Pre-shim send-capable bytecode must not survive in any ``__pycache__``.

``M-1`` STALE_SEND_CAPABLE_BYTECODE_SURVIVES (2026-07-20 residual re-audit, MEDIUM).

AE-1 replaced the 44,946-byte send-capable ``production_live_session.py`` with a
fail-closed shim, and the shim's own docstring asserts *"no second production
implementation survives anywhere on disk."*  That was false: the pre-shim
implementation survived as compiled bytecode in the out-of-repo
``__pycache__`` directories --

    phx2_production_private_live\\__pycache__\\production_live_session.cpython-312.pyc
    phx2_live_free_tier\\__pycache__\\free_tier_session.cpython-312.pyc

both compiled with the pinned interpreter's magic (3.12.10), both unmarshalling
to the send-capable ``main()`` with its arm gate intact, and neither carrying a
single reconnect-contract marker.  CPython runs a ``.pyc`` handed to it directly,
bypassing source-mtime validation, so ``python <stale>.pyc`` would execute the
bypassed path.

The neutralisation contract asserted here: no ``.pyc`` whose module is a
neutralised session shim may retain the pre-shim implementation, and no compiled
artifact under either external runtime root may retain the send arm gate.

The detector mechanism is proven against a BENIGN, locally generated fixture --
the real stale bytecode is never executed.  Everything else is a header decode
plus a raw-byte marker scan.  Nothing opens a socket, reads an environment file,
touches a credential, mutates a ledger or sends anything.
"""

from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_LIVE_ROOT = Path(r"C:\Users\BalaC\phx2_production_private_live")
FREE_TIER_ROOT = Path(r"C:\Users\BalaC\phx2_live_free_tier")

EXTERNAL_RUNTIME_ROOTS = (PRODUCTION_LIVE_ROOT, FREE_TIER_ROOT)

#: The neutralised session shims. A ``.pyc`` sibling of one of these that carries
#: the pre-shim implementation is a surviving send-capable artifact.
SHIM_MODULES = {
    PRODUCTION_LIVE_ROOT: "production_live_session",
    FREE_TIER_ROOT: "free_tier_session",
}

#: Raw-byte markers that only a send-capable session carries. The neutralised
#: shims contain none of them; the pre-shim implementations contain several.
ARM_GATE_MARKERS = (
    b"--i-understand-this-can-send",
    b"--confirm-token",
    b"--ack-live-free-tier",
    b"--ack-live-readonly-shadow",
    b"LOCKED_CONFIRM_TOKEN",
    b"AxiomFeeAppendingTransport",
    b"logsSubscribe",
)


def _pyc_header(raw: bytes) -> dict:
    """Decode a ``.pyc`` header without importing or executing it."""
    header = {"magic": struct.unpack("<H", raw[0:2])[0]}
    flags = struct.unpack("<I", raw[4:8])[0]
    header["hash_based"] = bool(flags & 0x1)
    if not header["hash_based"] and len(raw) >= 16:
        header["source_mtime"] = struct.unpack("<I", raw[8:12])[0]
        header["source_size"] = struct.unpack("<I", raw[12:16])[0]
    return header


def _arm_markers_in(raw: bytes) -> list:
    return sorted(m.decode() for m in ARM_GATE_MARKERS if m in raw)


def _is_send_capable_session_pyc(path: Path, shim_source: Path) -> bool:
    """True iff ``path`` is a session ``.pyc`` retaining the pre-shim body.

    Two independent tells, either sufficient: it carries an arm-gate marker the
    shim never had, or (for a timestamp-based ``.pyc``) its embedded source size
    does not match the current shim source -- i.e. it was compiled from a
    different, larger file that no longer exists on disk.
    """
    raw = path.read_bytes()
    if _arm_markers_in(raw):
        return True
    header = _pyc_header(raw)
    if not header["hash_based"] and "source_size" in header:
        try:
            current = shim_source.stat().st_size
        except OSError:
            return True
        if header["source_size"] != current:
            return True
    return False


def _session_pyc_files() -> list:
    """Every session-shim ``.pyc`` under both external runtime roots."""
    found = []
    for root, stem in SHIM_MODULES.items():
        cache = root / "__pycache__"
        if not cache.is_dir():
            continue
        found.extend(sorted(cache.glob(f"{stem}*.pyc")))
    return found


external_roots_present = pytest.mark.skipif(
    not any(root.exists() for root in EXTERNAL_RUNTIME_ROOTS),
    reason="external runtime roots absent on this machine",
)


# ---------------------------------------------------------------------------
# Detector mechanism, proven on a benign locally generated fixture.
# The real stale bytecode is NEVER executed.
# ---------------------------------------------------------------------------

def test_direct_pyc_execution_is_a_real_vector_benign_fixture(tmp_path):
    """A ``.pyc`` handed to CPython by path runs even with no source present.

    This is why a surviving send-capable ``.pyc`` matters: the module-selection
    guard (import prefers the shim) does not protect ``python <file>.pyc``.
    Proven with a throwaway module, never the real artifact.
    """
    import py_compile

    source = tmp_path / "benign_fixture.py"
    source.write_text(
        "import sys\nsys.stdout.write('BENIGN_PYC_RAN')\n", encoding="utf-8")
    compiled = tmp_path / "benign_fixture.pyc"
    py_compile.compile(str(source), cfile=str(compiled), doraise=True)
    source.unlink()  # prove execution does not depend on the source existing

    completed = subprocess.run(
        [sys.executable, "-B", str(compiled)],
        capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0
    assert "BENIGN_PYC_RAN" in completed.stdout


def test_arm_marker_detector_flags_benign_armed_bytecode(tmp_path):
    """The marker detector fires on send-capable bytecode and stays quiet on a
    clean shim -- established on benign fixtures, not the real artifacts."""
    import py_compile

    armed = tmp_path / "armed_fixture.py"
    armed.write_text(
        "FLAG = '--i-understand-this-can-send'\n"
        "TOKEN = 'LOCKED_CONFIRM_TOKEN'\n", encoding="utf-8")
    armed_pyc = tmp_path / "armed_fixture.pyc"
    py_compile.compile(str(armed), cfile=str(armed_pyc), doraise=True)
    assert _arm_markers_in(armed_pyc.read_bytes()), "detector missed armed bytecode"

    clean = tmp_path / "clean_shim.py"
    clean.write_text(
        "import sys\n\n\ndef main():\n    sys.stderr.write('refused')\n"
        "    return 2\n", encoding="utf-8")
    clean_pyc = tmp_path / "clean_shim.pyc"
    py_compile.compile(str(clean), cfile=str(clean_pyc), doraise=True)
    assert _arm_markers_in(clean_pyc.read_bytes()) == [], (
        "detector false-positived on a clean shim")


def test_stale_source_size_detector_flags_mismatched_bytecode(tmp_path):
    """A timestamp-based ``.pyc`` whose embedded source size no longer matches
    the on-disk source is flagged as stale (the real files' second tell)."""
    import py_compile

    big = tmp_path / "mod.py"
    big.write_text("VALUE = 1\n" * 400, encoding="utf-8")  # a large "pre-shim"
    stale_pyc = tmp_path / "mod.pyc"
    py_compile.compile(str(big), cfile=str(stale_pyc), doraise=True)
    big.write_text("VALUE = 1\n", encoding="utf-8")  # shrink to a "shim"
    assert _is_send_capable_session_pyc(stale_pyc, big) is True


# ---------------------------------------------------------------------------
# The real assertions: no surviving send-capable session bytecode.
# ---------------------------------------------------------------------------

@external_roots_present
def test_no_session_shim_retains_send_capable_bytecode():
    """No ``production_live_session`` / ``free_tier_session`` ``.pyc`` sibling of
    a neutralised shim may retain the pre-shim send-capable implementation."""
    offenders = []
    for root, stem in SHIM_MODULES.items():
        shim_source = root / f"{stem}.py"
        cache = root / "__pycache__"
        if not cache.is_dir():
            continue
        for pyc in sorted(cache.glob(f"{stem}*.pyc")):
            if _is_send_capable_session_pyc(pyc, shim_source):
                offenders.append(
                    f"{pyc} markers={_arm_markers_in(pyc.read_bytes())}")
    assert not offenders, (
        "surviving send-capable session bytecode:\n" + "\n".join(offenders))


@external_roots_present
def test_no_external_runtime_bytecode_retains_the_arm_gate():
    """Nothing compiled under either external runtime root may retain the send
    arm gate -- not the session shims and not any legacy runner module."""
    offenders = []
    for root in EXTERNAL_RUNTIME_ROOTS:
        if not root.exists():
            continue
        for pyc in sorted(root.rglob("*.pyc")):
            markers = _arm_markers_in(pyc.read_bytes())
            if markers:
                offenders.append(f"{pyc} markers={markers}")
    assert not offenders, (
        "compiled bytecode still carries the arm gate:\n" + "\n".join(offenders))


@external_roots_present
def test_neutralised_shim_has_no_send_capable_pyc_sibling():
    """Cache-safety: replacing an implementation with a shim must not leave an
    older send-capable ``.pyc`` beside it (the source-shim cleanup contract)."""
    for root, stem in SHIM_MODULES.items():
        shim_source = root / f"{stem}.py"
        if not shim_source.is_file():
            continue
        # The current shim itself must be small and marker-free.
        assert not _arm_markers_in(shim_source.read_bytes())
        cache = root / "__pycache__"
        if not cache.is_dir():
            continue
        siblings = list(cache.glob(f"{stem}*.pyc"))
        for pyc in siblings:
            assert not _is_send_capable_session_pyc(pyc, shim_source), (
                f"{pyc.name} is a send-capable sibling of the {stem} shim")


def test_generated_bytecode_and_caches_stay_gitignored():
    """Generated bytecode and cache directories must remain ignored so a
    recompiled artifact is never committed into the tracked tree."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in gitignore.splitlines()}
    assert "__pycache__/" in lines
    assert "*.pyc" in lines or "*.py[cod]" in lines
