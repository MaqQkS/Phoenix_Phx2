#!/usr/bin/env python3
"""Thin script entry for the Stage 19 operator review ledger builder.

Inserts the PHX2 repo root onto ``sys.path`` (so direct
``python PHX2/scripts/run_stage19_review.py`` invocation resolves
the ``PHX2`` package), then delegates to ``PHX2.stage19.cli.main``.

Operators who prefer:

    python PHX2/scripts/run_stage19_review.py

can use this shim instead of:

    python -m PHX2.stage19.cli

All argument parsing, validation, and orchestration live in
``PHX2.stage19.cli``; this file adds no logic of its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    _repo_root = str(Path(__file__).resolve().parents[2])
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from PHX2.stage19.cli import main


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
