"""Centralized closed-set, artifact-safe market/current-data source labels.

``current_data_source`` is persisted provenance *telemetry*: it is written when a
candidate is constructed, carried on the watchlist record, serialized into
``watch_state.jsonl`` / ``phx2_ping_quality_review.jsonl``, and displayed.  No
runtime decision is ever taken on its value.

Because those artifacts are governed by the credential-redaction scanner, the
label vocabulary itself must be artifact-safe: it may name the *role* a source
plays, never the provider product behind it.  A provider-named value
(``birdeye``, ``chainstack``, ...) is a scanner danger needle and fails the run
closed with ``SECRET_SCAN_FAILURE`` even though no credential is present — this
is exactly what killed the 2026-07-30 canary every ~2.5 minutes.

The closed set distinguishes the four authorities the operator must be able to
tell apart:

- ``PAID_MARKET_PRIMARY_AND_LIVE_MIGRATION_PRIMARY`` — paid market-data
  authority combined with the live migration-source authority.
- ``PAID_PRIMARY_AND_CANONICAL_RESERVES`` — paid market-data authority combined
  with canonical on-chain pool-reserve evidence.
- ``DEXSCREENER_PAIR`` — bounded six-hour DEX backfill pair evidence.  This one
  token is an explicitly allowlisted public schema value of the restart-backfill
  contract (see ``FIXED_PUBLIC_REDACTION_TOKENS``), not a provider leak.
- ``MARKET_SOURCE_UNAVAILABLE`` — degraded/unavailable market authority, used
  when required market evidence could not be obtained.

Unknown values are never coerced.  ``normalize_market_data_source`` maps only
the exact retired label to its artifact-safe replacement so any legacy persisted
record round-trips without re-emitting a danger needle.
"""

from __future__ import annotations

from typing import Optional

MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION = (
    "PAID_MARKET_PRIMARY_AND_LIVE_MIGRATION_PRIMARY")
MARKET_DATA_SOURCE_PAID_MARKET_AND_CANONICAL_RESERVES = (
    "PAID_PRIMARY_AND_CANONICAL_RESERVES")
MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR = "DEXSCREENER_PAIR"
MARKET_DATA_SOURCE_UNAVAILABLE = "MARKET_SOURCE_UNAVAILABLE"

#: The complete closed set.  Order is stable for artifacts and tests.
MARKET_DATA_SOURCES = (
    MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION,
    MARKET_DATA_SOURCE_PAID_MARKET_AND_CANONICAL_RESERVES,
    MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR,
    MARKET_DATA_SOURCE_UNAVAILABLE,
)

#: Retired provider-named label -> artifact-safe replacement.  Kept private to
#: the module: it is a migration table, never serialized into an artifact.
_RETIRED_MARKET_DATA_SOURCE_ALIASES = {
    "BIRDEYE_AND_HELIUS_PRIMARY":
        MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION,
}


def is_known_market_data_source(value: object) -> bool:
    """True only for exact members of the closed set; no coercion."""

    return value in MARKET_DATA_SOURCES


def normalize_market_data_source(value: object) -> Optional[str]:
    """Return the artifact-safe label for ``value``.

    Exact closed-set members pass through unchanged.  The one retired
    provider-named label is mapped to its replacement so a legacy persisted
    record never re-emits a danger needle.  Anything else (including ``None``)
    is returned unchanged so unknown values stay visible to the scanner and to
    explicit downstream rejection rather than being silently rewritten.
    """

    if isinstance(value, str):
        return _RETIRED_MARKET_DATA_SOURCE_ALIASES.get(value, value)
    return value  # type: ignore[return-value]


__all__ = (
    "MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION",
    "MARKET_DATA_SOURCE_PAID_MARKET_AND_CANONICAL_RESERVES",
    "MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR",
    "MARKET_DATA_SOURCE_UNAVAILABLE",
    "MARKET_DATA_SOURCES",
    "is_known_market_data_source",
    "normalize_market_data_source",
)
