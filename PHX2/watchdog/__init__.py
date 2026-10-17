"""PHX2 watchdog: the operational wrapper that keeps ONE armed producer alive.

Stage 10 is deployment and reliability work only.  Nothing in this package
participates in discovery, census, reconciliation, 1.20x tracking, structural
policy, candidate filters, dip tiers, alert contents, dedupe identity, ledger
format, Telegram transport semantics, paper trading or dashboard logic.

The runtime architecture the watchdog wraps is the ACCEPTED one and is not
re-opened here:

    Windows Task Scheduler
      -> PHX2 watchdog                      (this package)
        -> launch_live_24x7.ps1             (canonical external launcher)
          -> PHX2.free_tier_producer.free_tier_session   (the ONE armed producer)
            -> one Yellowstone owner
            -> one private Telegram destination
            -> one canonical paid-ledger writer

Accepted finding ``M-2`` stays closed: the watchdog never invokes
``PHX2/main.py`` or ``PHX2.runtime.production_supervisor``, and never builds a
producer argument vector of its own.  It launches the canonical launcher and
nothing else, so there is exactly one place where the armed vector is written.

Ownership is strictly partitioned.  The watchdog owns ONLY its own lock and its
own observability files.  It cannot construct a transport, cannot open the
canonical ledger writable, cannot mutate cursor or recovery state, and cannot
own a Yellowstone stream -- those are producer-owned resources and the tests in
``PHX2/tests/watchdog`` prove the watchdog source contains no path to them.
"""

from __future__ import annotations

WATCHDOG_PACKAGE_VERSION = "PHX2_WATCHDOG_STAGE10_V1"

__all__ = ("WATCHDOG_PACKAGE_VERSION",)
