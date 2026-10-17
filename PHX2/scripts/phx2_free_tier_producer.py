"""Thin launcher for the tracked PHX2 free-tier producer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence


_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PHX2.free_tier_producer.free_tier_session import main as _producer_main  # noqa: E402


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Forward the CLI unchanged; arming and confirmation stay in the producer."""

    return _producer_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
