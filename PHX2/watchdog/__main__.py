"""``python -m PHX2.watchdog <action>``."""

from __future__ import annotations

import sys

from PHX2.watchdog.daemon import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
