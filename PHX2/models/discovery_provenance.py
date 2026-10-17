"""Centralized closed-set discovery-provenance contract.

One shared vocabulary for every production producer and consumer of
``discovery_provenance``.  The closed set is exactly three values:

- ``LIVE_YELLOWSTONE`` — authoritative live discovery decoded from the paid
  Yellowstone gRPC stream (legacy live source).
- ``LIVE_HELIUS`` — authoritative live discovery decoded from the Helius
  enhanced WSS stream (current live source).  It is a LIVE provenance with the
  same authority, activation multiplier, epoch binding, and freshness rules as
  ``LIVE_YELLOWSTONE`` — never a compatibility alias for it.
- ``DEXSCREENER_RESTART_BACKFILL`` — bounded (six-hour) restart/periodic DEX
  candidate recovery with explicit inferred-migration evidence.  It is the only
  provenance whose candidates may carry a migration time earlier than the
  current live epoch boundary.

Unknown values are never coerced: membership helpers return ``False`` and the
consumer applies its own explicit rejection (``SEED_OUTCOME_INVALID``,
``DISCOVERY_PROVENANCE_INVALID``, ...).  Source labels never decide candidate
dedupe behavior — the candidate-level ``provider_dedupe_applied`` stamp
(dfb1664) remains the single dedupe authority.
"""

from __future__ import annotations

DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE = "LIVE_YELLOWSTONE"
DISCOVERY_PROVENANCE_LIVE_HELIUS = "LIVE_HELIUS"
DISCOVERY_PROVENANCE_DEX_BACKFILL = "DEXSCREENER_RESTART_BACKFILL"

#: Authoritative live discovery (post-epoch-boundary candidates only).
LIVE_DISCOVERY_PROVENANCES = (
    DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE,
    DISCOVERY_PROVENANCE_LIVE_HELIUS,
)

#: Bounded recovery provenances whose candidates may pre-date the live epoch.
BACKFILL_DISCOVERY_PROVENANCES = (
    DISCOVERY_PROVENANCE_DEX_BACKFILL,
)

#: The complete closed set.  Order is stable for artifacts and tests.
DISCOVERY_PROVENANCES = (
    LIVE_DISCOVERY_PROVENANCES + BACKFILL_DISCOVERY_PROVENANCES
)


def is_live_discovery_provenance(value: object) -> bool:
    """True only for the exact closed-set live provenance strings."""

    return value in LIVE_DISCOVERY_PROVENANCES


def is_backfill_discovery_provenance(value: object) -> bool:
    """True only for the exact closed-set bounded-backfill provenance."""

    return value in BACKFILL_DISCOVERY_PROVENANCES


def is_known_discovery_provenance(value: object) -> bool:
    """True only for exact members of the closed set; no coercion."""

    return value in DISCOVERY_PROVENANCES


__all__ = (
    "DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE",
    "DISCOVERY_PROVENANCE_LIVE_HELIUS",
    "DISCOVERY_PROVENANCE_DEX_BACKFILL",
    "LIVE_DISCOVERY_PROVENANCES",
    "BACKFILL_DISCOVERY_PROVENANCES",
    "DISCOVERY_PROVENANCES",
    "is_live_discovery_provenance",
    "is_backfill_discovery_provenance",
    "is_known_discovery_provenance",
)
