"""Thin script entry for Stage 16A.

Inserts the PHX2 repo root onto sys.path (so direct ``python PHX2/scripts/run_stage16a.py``
invocation resolves the ``PHX2`` package), then delegates to ``PHX2.stage16a.cli.main``.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    _repo_root = str(Path(__file__).resolve().parents[2])
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from PHX2.stage16a.cli import main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
