"""Build #23 supervised-entrypoint package (the repo-side launch boundary).

This package is the thin, repo-side launch boundary that ``PHX2/main.py``
delegates to for the ``--mode private-supervised`` actions. It VALIDATES operator
inputs and SUBPROCESSES the already-proven, out-of-repo supervised private
operator flow. It builds no second send path: it constructs no transport, no
authorization sentinel, and never flips an arm. ``--live`` only LAUNCHES the
supervised flow; the interactive human approval, the one-line arm flip, and the
single private operator send all remain INSIDE the out-of-repo supervisor.

Importing this package performs no I/O, opens no network connection, reads no
credential, and spawns no process (no module-level side effects).
"""

from __future__ import annotations

__all__ = ()
