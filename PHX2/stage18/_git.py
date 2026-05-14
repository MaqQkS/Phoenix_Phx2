"""Stage 18 git-commit capture (the sole subprocess user in Stage 18).

Isolating the ``subprocess`` import to this module lets the
boundary tests assert that no other Stage 18 source file shells
out. Capturing the commit is non-fatal: any failure -- missing
git binary, timeout, nonzero exit, or malformed output -- is
swallowed and the function returns the sentinel string
``"unknown"``. Callers embed the return value verbatim into the
Stage 18 manifest's ``git_commit`` field.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


_HEX_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def get_git_commit() -> str:
    """Return ``HEAD``'s commit SHA, or ``"unknown"`` on any failure.

    Never raises. Errors handled silently:

      * git binary not present on PATH (``FileNotFoundError``).
      * git returned non-zero (``CalledProcessError``).
      * subprocess timeout (2 seconds).
      * OS-level subprocess failure.
      * Output is not a 40-character lowercase hex hash.

    The two-second timeout is a hard cap so a wedged git process
    cannot stall a report build.
    """

    repo_root = Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return "unknown"
    sha = proc.stdout.strip()
    if _HEX_SHA_RE.match(sha):
        return sha
    return "unknown"


__all__ = ["get_git_commit"]
