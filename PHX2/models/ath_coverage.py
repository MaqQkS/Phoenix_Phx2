"""Centralized closed-set post-migration ATH coverage contract.

Before this module the coverage classification existed only in the Telegram
presentation layer: ``telegram_adapter`` derived ``PARTIAL_SINCE_ADMISSION``
from ``discovery_provenance`` and rendered it as a body line, while NOTHING in
the compose / tier / send authorization path consumed it.  The 2026-07-30
canary sent a Tier 1 alert on a ``DEXSCREENER_RESTART_BACKFILL`` candidate
whose displayed maximum was only the highest CURRENT market cap observed since
PHX2 admitted it (5 minutes of a 13-minute post-migration life) -- the body
honestly said "Coverage: Partial (restart backfill)" and the alert went out
anyway.

One vocabulary, consumed by the send path and by presentation, so a partial
maximum can never reach a tier or a transport:

- ``COMPLETE_LIVE``      -- live discovery (Yellowstone / Helius).  PHX2 saw
  the mint from its migration onward, so its running maximum IS the complete
  post-migration ATH.  Unchanged behaviour.
- ``COMPLETE_HYDRATED``  -- a bounded-backfill candidate whose migration-
  anchored OHLCV history has been fetched to completion and verified
  (:mod:`PHX2.free_tier_producer.ath_state` owns that proof).  Its maximum is
  the complete post-migration ATH even though PHX2 admitted it late.
- ``PARTIAL_SINCE_ADMISSION`` -- a bounded-backfill candidate still hydrating.
  Retained, retried, disclosed -- never tiered, composed or sent.
- ``UNKNOWN``            -- provenance PHX2 cannot classify.  Fail closed.

Only the two COMPLETE tokens authorize a tier, a compose or a send.
"""

from __future__ import annotations

from PHX2.models.discovery_provenance import (
    is_backfill_discovery_provenance,
    is_live_discovery_provenance,
)

# --- Coverage tokens -------------------------------------------------------

ATH_COVERAGE_COMPLETE_LIVE = "COMPLETE_LIVE"
ATH_COVERAGE_COMPLETE_HYDRATED = "COMPLETE_HYDRATED"
ATH_COVERAGE_PARTIAL_SINCE_ADMISSION = "PARTIAL_SINCE_ADMISSION"
ATH_COVERAGE_UNKNOWN = "UNKNOWN"

#: Stable order for artifacts and tests.
ATH_COVERAGE_TOKENS = (
    ATH_COVERAGE_COMPLETE_LIVE,
    ATH_COVERAGE_COMPLETE_HYDRATED,
    ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
    ATH_COVERAGE_UNKNOWN,
)

#: The ONLY tokens that authorize a tier projection, a compose or a send.
ATH_COVERAGE_SEND_ELIGIBLE = (
    ATH_COVERAGE_COMPLETE_LIVE,
    ATH_COVERAGE_COMPLETE_HYDRATED,
)

# --- Hydration status tokens ----------------------------------------------
# Owned and produced by the central ATH store; consumed here and by the
# compose / delivery path.

ATH_HYDRATION_COMPLETE = "ATH_HYDRATION_COMPLETE"
ATH_HYDRATION_PENDING = "ATH_HYDRATION_PENDING"
ATH_HYDRATION_STATUSES = (ATH_HYDRATION_COMPLETE, ATH_HYDRATION_PENDING)

#: Closed-set reasons a candidate's post-migration history is not yet proven.
ATH_HYDRATION_NEVER_ATTEMPTED = "ATH_HYDRATION_NEVER_ATTEMPTED"
ATH_HYDRATION_WINDOW_INCOMPLETE = "ATH_HYDRATION_WINDOW_INCOMPLETE"
ATH_HYDRATION_ANCHOR_MISSING = "ATH_HYDRATION_ANCHOR_MISSING"
ATH_HYDRATION_WINDOW_STARTS_AFTER_MIGRATION = (
    "ATH_HYDRATION_WINDOW_STARTS_AFTER_MIGRATION")
ATH_HYDRATION_WINDOW_STALE = "ATH_HYDRATION_WINDOW_STALE"
ATH_HYDRATION_MARKET_CAP_UNCONVERTED = "ATH_HYDRATION_MARKET_CAP_UNCONVERTED"
ATH_HYDRATION_VERIFIED = "ATH_HYDRATION_VERIFIED"

# ---- V3 pair-history pending reasons (2026-08-03) -------------------------
# One specific reason per distinct V3 failure shape, never collapsed into a
# generic UNKNOWN/NOT_DISPATCHABLE/MARKET_INCOMPLETE.  Each pends exactly ONE
# candidate; systemic failure is a health-surface concern, not a new circuit.
ATH_V3_HISTORY_INCOMPLETE = "ATH_V3_HISTORY_INCOMPLETE"
ATH_V3_AUTH_FAILED = "ATH_V3_AUTH_FAILED"
ATH_V3_RATE_LIMITED = "ATH_V3_RATE_LIMITED"
ATH_V3_PAIR_UNAVAILABLE = "ATH_V3_PAIR_UNAVAILABLE"
ATH_V3_CANDLE_GAP = "ATH_V3_CANDLE_GAP"
ATH_V3_INVERSION_UNRESOLVED = "ATH_V3_INVERSION_UNRESOLVED"
#: The pair-native peak is proven but no validated USD valuation of that
#: exact candle exists yet (token/pair series disagree at the peak second and
#: no volume-matched conversion window survived validation).
ATH_V3_USD_CONVERSION_UNRESOLVED = "ATH_V3_USD_CONVERSION_UNRESOLVED"

ATH_V3_PENDING_REASONS = (
    ATH_V3_HISTORY_INCOMPLETE,
    ATH_V3_AUTH_FAILED,
    ATH_V3_RATE_LIMITED,
    ATH_V3_PAIR_UNAVAILABLE,
    ATH_V3_CANDLE_GAP,
    ATH_V3_INVERSION_UNRESOLVED,
    ATH_V3_USD_CONVERSION_UNRESOLVED,
)

ATH_HYDRATION_REASONS = (
    ATH_HYDRATION_NEVER_ATTEMPTED,
    ATH_HYDRATION_WINDOW_INCOMPLETE,
    ATH_HYDRATION_ANCHOR_MISSING,
    ATH_HYDRATION_WINDOW_STARTS_AFTER_MIGRATION,
    ATH_HYDRATION_WINDOW_STALE,
    ATH_HYDRATION_MARKET_CAP_UNCONVERTED,
    ATH_HYDRATION_VERIFIED,
) + ATH_V3_PENDING_REASONS

# ---- canonical ATH path source tokens (2026-08-03) ------------------------
# Which allowed path proved the complete post-migration maximum.  The paid
# provider's V3 PAIR history is the canonical source; the uninterrupted
# live tracker is the sanctioned fallback while V3 is unavailable.  Values
# are ROLE-based on purpose: a provider product name is a run-killing danger
# needle in every scanned artifact (see PHX2.models.artifact_source_labels),
# so the V3-pair token names the surface, never the vendor.
ATH_CANONICAL_SOURCE_V3_PAIR = "PAID_V3_PAIR_OHLCV_COMPLETE"
ATH_CANONICAL_SOURCE_LIVE_TRACKER = "LIVE_TRACKER_COMPLETE"
ATH_CANONICAL_SOURCES = (
    ATH_CANONICAL_SOURCE_V3_PAIR,
    ATH_CANONICAL_SOURCE_LIVE_TRACKER,
)

#: Compose/send refusal reason when coverage is not proven complete.
COMPOSE_REJECTED_ATH_COVERAGE_INCOMPLETE = (
    "COMPOSE_REJECTED_ATH_COVERAGE_INCOMPLETE")


def classify_ath_coverage(
    *, discovery_provenance: object, ath_hydration_status: object = None
) -> str:
    """Closed-set coverage token for one candidate.  Never coerces.

    2026-08-03 correction: a live provenance is no longer COMPLETE merely by
    having been discovered live.  The last real alert proved why -- the paid
    polling topology samples the market, and the literal post-migration peak
    (first 15 seconds after migration) sat between polls AND inside an OHLCV
    candle the old window request dropped.  Live provenance is COMPLETE only
    when the central ATH store's hydration verdict says the maximum is proven
    (canonical V3 pair history, or the uninterrupted live tracker while V3 is
    unavailable).  A caller that supplies NO hydration status (legacy/offline
    consumers that predate the verdict) keeps the historical live-is-complete
    reading -- absence of the new evidence channel must not retroactively
    reclassify old artifacts.

    A bounded-backfill provenance is COMPLETE only once the central ATH store
    has PROVEN a complete migration-anchored history; until then it is
    explicitly partial.  Anything else is UNKNOWN and fails closed downstream.
    """

    if is_live_discovery_provenance(discovery_provenance):
        if (ath_hydration_status is None
                or ath_hydration_status == ATH_HYDRATION_COMPLETE):
            return ATH_COVERAGE_COMPLETE_LIVE
        return ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
    if is_backfill_discovery_provenance(discovery_provenance):
        if ath_hydration_status == ATH_HYDRATION_COMPLETE:
            return ATH_COVERAGE_COMPLETE_HYDRATED
        return ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
    return ATH_COVERAGE_UNKNOWN


def ath_coverage_is_complete(value: object) -> bool:
    """True only for a token that proves complete post-migration coverage."""

    return value in ATH_COVERAGE_SEND_ELIGIBLE


__all__ = (
    "ATH_COVERAGE_COMPLETE_LIVE",
    "ATH_COVERAGE_COMPLETE_HYDRATED",
    "ATH_COVERAGE_PARTIAL_SINCE_ADMISSION",
    "ATH_COVERAGE_UNKNOWN",
    "ATH_COVERAGE_TOKENS",
    "ATH_COVERAGE_SEND_ELIGIBLE",
    "ATH_HYDRATION_COMPLETE",
    "ATH_HYDRATION_PENDING",
    "ATH_HYDRATION_STATUSES",
    "ATH_HYDRATION_NEVER_ATTEMPTED",
    "ATH_HYDRATION_WINDOW_INCOMPLETE",
    "ATH_HYDRATION_ANCHOR_MISSING",
    "ATH_HYDRATION_WINDOW_STARTS_AFTER_MIGRATION",
    "ATH_HYDRATION_WINDOW_STALE",
    "ATH_HYDRATION_MARKET_CAP_UNCONVERTED",
    "ATH_HYDRATION_VERIFIED",
    "ATH_V3_HISTORY_INCOMPLETE",
    "ATH_V3_AUTH_FAILED",
    "ATH_V3_RATE_LIMITED",
    "ATH_V3_PAIR_UNAVAILABLE",
    "ATH_V3_CANDLE_GAP",
    "ATH_V3_INVERSION_UNRESOLVED",
    "ATH_V3_USD_CONVERSION_UNRESOLVED",
    "ATH_V3_PENDING_REASONS",
    "ATH_CANONICAL_SOURCE_V3_PAIR",
    "ATH_CANONICAL_SOURCE_LIVE_TRACKER",
    "ATH_CANONICAL_SOURCES",
    "ATH_HYDRATION_REASONS",
    "COMPOSE_REJECTED_ATH_COVERAGE_INCOMPLETE",
    "classify_ath_coverage",
    "ath_coverage_is_complete",
)
