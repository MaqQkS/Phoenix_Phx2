"""Stage 27.2 pair-detection closed-set vocabularies and known mints.

Stage 27.2 ships the closed-set vocabularies, the known SOL / USDC
quote-mint constants, and the version axes used by the deterministic
pair classifier skeleton. Every closed-set value is a plain string
literal so a downstream test can pin the exact tuple membership.

Closed-set vocabularies:

  * ``QUOTE_ASSET``                 -- ``SOL`` / ``USDC`` / ``UNKNOWN``
  * ``PAIR_TYPE``                   -- ``PUMP_SOL`` / ``PUMP_USDC`` /
                                       ``UNKNOWN``
  * ``BONDING_CURVE_VERSION``       -- ``SOL_LEGACY`` / ``USDC_FIXED``
                                       / ``UNKNOWN``
  * ``PAIR_DETECTION_STATUS``       -- ``CONFIRMED`` / ``PROVIDER_ONLY``
                                       / ``DISAGREE`` / ``UNRESOLVED``
  * ``PAIR_DETECTION_CONFIDENCE``   -- ``HIGH`` / ``MEDIUM`` / ``LOW``
                                       / ``NONE``
  * ``PAIR_DETECTION_SOURCE``       -- ``POOL_QUOTE_MINT`` /
                                       ``BONDING_CURVE_METADATA`` /
                                       ``MIGRATION_EVENT`` /
                                       ``PROVIDER_PAYLOAD`` /
                                       ``KNOWN_MINT_FALLBACK``
  * ``LIVE_POLICY``                 -- ``LIVE_ALLOWED`` /
                                       ``LIVE_SUPPRESS_UNKNOWN`` /
                                       ``LIVE_SUPPRESS_DISAGREE`` /
                                       ``DRY_RUN_ONLY``
  * ``CALIBRATION_LANE``            -- ``EXISTING_SOL_LANE`` /
                                       ``USDC_OBSERVE_ONLY`` /
                                       ``UNKNOWN_PAIR_OBSERVE_ONLY`` /
                                       ``DISAGREE_PAIR_OBSERVE_ONLY``
  * ``PAIR_DETECTION_REASON``       -- closed-set reason codes
                                       describing the resolution path.

Known mint constants:

  * ``KNOWN_WRAPPED_SOL_MINT``      -- the canonical wrapped-SOL SPL
                                       mint address.
  * ``KNOWN_USDC_MINT``             -- the canonical mainnet USDC SPL
                                       mint address.

Both mint constants are matched exactly. An unknown / missing
quote-mint string must never be silently promoted to SOL.

This module imports only stdlib (``typing``). It does NOT import
Stage 21-26 production code, does NOT import any network / RPC /
messaging / DB / scheduler / secrets-management library, does NOT
read the process environment, does NOT define a CLI surface, and
contains no top-level I/O.
"""

from __future__ import annotations

from typing import Mapping


# ---------------------------------------------------------------------------
# Stage 27.2 version axes
# ---------------------------------------------------------------------------


STAGE27_2_MINOR_VERSION: str = "27.2"
STAGE27_2_SCHEMA_VERSION: str = "stage27_v0_pair_detection"


# ---------------------------------------------------------------------------
# quote_asset closed set
# ---------------------------------------------------------------------------


QUOTE_ASSET_SOL: str = "SOL"
QUOTE_ASSET_USDC: str = "USDC"
QUOTE_ASSET_UNKNOWN: str = "UNKNOWN"

QUOTE_ASSET_VALUES: tuple[str, ...] = (
    QUOTE_ASSET_SOL,
    QUOTE_ASSET_USDC,
    QUOTE_ASSET_UNKNOWN,
)


# ---------------------------------------------------------------------------
# pair_type closed set
# ---------------------------------------------------------------------------


PAIR_TYPE_PUMP_SOL: str = "PUMP_SOL"
PAIR_TYPE_PUMP_USDC: str = "PUMP_USDC"
PAIR_TYPE_UNKNOWN: str = "UNKNOWN"

PAIR_TYPE_VALUES: tuple[str, ...] = (
    PAIR_TYPE_PUMP_SOL,
    PAIR_TYPE_PUMP_USDC,
    PAIR_TYPE_UNKNOWN,
)


# ---------------------------------------------------------------------------
# bonding_curve_version closed set
# ---------------------------------------------------------------------------


BONDING_CURVE_VERSION_SOL_LEGACY: str = "SOL_LEGACY"
BONDING_CURVE_VERSION_USDC_FIXED: str = "USDC_FIXED"
BONDING_CURVE_VERSION_UNKNOWN: str = "UNKNOWN"

BONDING_CURVE_VERSION_VALUES: tuple[str, ...] = (
    BONDING_CURVE_VERSION_SOL_LEGACY,
    BONDING_CURVE_VERSION_USDC_FIXED,
    BONDING_CURVE_VERSION_UNKNOWN,
)


# ---------------------------------------------------------------------------
# pair_detection_status closed set
# ---------------------------------------------------------------------------


PAIR_DETECTION_STATUS_CONFIRMED: str = "CONFIRMED"
PAIR_DETECTION_STATUS_PROVIDER_ONLY: str = "PROVIDER_ONLY"
PAIR_DETECTION_STATUS_DISAGREE: str = "DISAGREE"
PAIR_DETECTION_STATUS_UNRESOLVED: str = "UNRESOLVED"

PAIR_DETECTION_STATUS_VALUES: tuple[str, ...] = (
    PAIR_DETECTION_STATUS_CONFIRMED,
    PAIR_DETECTION_STATUS_PROVIDER_ONLY,
    PAIR_DETECTION_STATUS_DISAGREE,
    PAIR_DETECTION_STATUS_UNRESOLVED,
)


# ---------------------------------------------------------------------------
# pair_detection_confidence closed set
# ---------------------------------------------------------------------------


PAIR_DETECTION_CONFIDENCE_HIGH: str = "HIGH"
PAIR_DETECTION_CONFIDENCE_MEDIUM: str = "MEDIUM"
PAIR_DETECTION_CONFIDENCE_LOW: str = "LOW"
PAIR_DETECTION_CONFIDENCE_NONE: str = "NONE"

PAIR_DETECTION_CONFIDENCE_VALUES: tuple[str, ...] = (
    PAIR_DETECTION_CONFIDENCE_HIGH,
    PAIR_DETECTION_CONFIDENCE_MEDIUM,
    PAIR_DETECTION_CONFIDENCE_LOW,
    PAIR_DETECTION_CONFIDENCE_NONE,
)


# ---------------------------------------------------------------------------
# pair_detection_source closed set (strongest first)
# ---------------------------------------------------------------------------


PAIR_DETECTION_SOURCE_POOL_QUOTE_MINT: str = "POOL_QUOTE_MINT"
PAIR_DETECTION_SOURCE_BONDING_CURVE_METADATA: str = (
    "BONDING_CURVE_METADATA"
)
PAIR_DETECTION_SOURCE_MIGRATION_EVENT: str = "MIGRATION_EVENT"
PAIR_DETECTION_SOURCE_PROVIDER_PAYLOAD: str = "PROVIDER_PAYLOAD"
PAIR_DETECTION_SOURCE_KNOWN_MINT_FALLBACK: str = "KNOWN_MINT_FALLBACK"

PAIR_DETECTION_SOURCE_VALUES: tuple[str, ...] = (
    PAIR_DETECTION_SOURCE_POOL_QUOTE_MINT,
    PAIR_DETECTION_SOURCE_BONDING_CURVE_METADATA,
    PAIR_DETECTION_SOURCE_MIGRATION_EVENT,
    PAIR_DETECTION_SOURCE_PROVIDER_PAYLOAD,
    PAIR_DETECTION_SOURCE_KNOWN_MINT_FALLBACK,
)


# Source-strength tiers. The classifier consults these tiers to
# decide which evidence dominates which, and to label disagreement
# severity.
PAIR_DETECTION_SOURCES_STRONG: tuple[str, ...] = (
    PAIR_DETECTION_SOURCE_POOL_QUOTE_MINT,
    PAIR_DETECTION_SOURCE_BONDING_CURVE_METADATA,
)
PAIR_DETECTION_SOURCES_MIDDLE: tuple[str, ...] = (
    PAIR_DETECTION_SOURCE_MIGRATION_EVENT,
)
PAIR_DETECTION_SOURCES_WEAK: tuple[str, ...] = (
    PAIR_DETECTION_SOURCE_PROVIDER_PAYLOAD,
    PAIR_DETECTION_SOURCE_KNOWN_MINT_FALLBACK,
)


# ---------------------------------------------------------------------------
# live_policy closed set
# ---------------------------------------------------------------------------


LIVE_POLICY_LIVE_ALLOWED: str = "LIVE_ALLOWED"
LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN: str = "LIVE_SUPPRESS_UNKNOWN"
LIVE_POLICY_LIVE_SUPPRESS_DISAGREE: str = "LIVE_SUPPRESS_DISAGREE"
LIVE_POLICY_DRY_RUN_ONLY: str = "DRY_RUN_ONLY"

LIVE_POLICY_VALUES: tuple[str, ...] = (
    LIVE_POLICY_LIVE_ALLOWED,
    LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
    LIVE_POLICY_LIVE_SUPPRESS_DISAGREE,
    LIVE_POLICY_DRY_RUN_ONLY,
)


# ---------------------------------------------------------------------------
# calibration_lane closed set
# ---------------------------------------------------------------------------


CALIBRATION_LANE_EXISTING_SOL_LANE: str = "EXISTING_SOL_LANE"
CALIBRATION_LANE_USDC_OBSERVE_ONLY: str = "USDC_OBSERVE_ONLY"
CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY: str = (
    "UNKNOWN_PAIR_OBSERVE_ONLY"
)
CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY: str = (
    "DISAGREE_PAIR_OBSERVE_ONLY"
)

CALIBRATION_LANE_VALUES: tuple[str, ...] = (
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    CALIBRATION_LANE_USDC_OBSERVE_ONLY,
    CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
)


# ---------------------------------------------------------------------------
# pair_detection_reason closed set
# ---------------------------------------------------------------------------


PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT: str = "CONFIRMED_AGREEMENT"
PAIR_DETECTION_REASON_SINGLE_STRONG_SOURCE: str = (
    "SINGLE_STRONG_SOURCE"
)
PAIR_DETECTION_REASON_PROVIDER_ONLY_EVIDENCE: str = (
    "PROVIDER_ONLY_EVIDENCE"
)
PAIR_DETECTION_REASON_MIGRATION_HINT_ONLY: str = (
    "MIGRATION_HINT_ONLY"
)
PAIR_DETECTION_REASON_STRONG_SOURCE_DISAGREE: str = (
    "STRONG_SOURCE_DISAGREE"
)
PAIR_DETECTION_REASON_QUOTE_MINT_VS_PROVIDER_DISAGREE: str = (
    "QUOTE_MINT_VS_PROVIDER_DISAGREE"
)
PAIR_DETECTION_REASON_BONDING_CURVE_VS_QUOTE_MINT_DISAGREE: str = (
    "BONDING_CURVE_VS_QUOTE_MINT_DISAGREE"
)
PAIR_DETECTION_REASON_PROVIDER_INTERNAL_INCONSISTENT: str = (
    "PROVIDER_INTERNAL_INCONSISTENT"
)
PAIR_DETECTION_REASON_NO_EVIDENCE: str = "NO_EVIDENCE"
PAIR_DETECTION_REASON_MALFORMED_QUOTE_MINT: str = (
    "MALFORMED_QUOTE_MINT"
)

PAIR_DETECTION_REASON_VALUES: tuple[str, ...] = (
    PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
    PAIR_DETECTION_REASON_SINGLE_STRONG_SOURCE,
    PAIR_DETECTION_REASON_PROVIDER_ONLY_EVIDENCE,
    PAIR_DETECTION_REASON_MIGRATION_HINT_ONLY,
    PAIR_DETECTION_REASON_STRONG_SOURCE_DISAGREE,
    PAIR_DETECTION_REASON_QUOTE_MINT_VS_PROVIDER_DISAGREE,
    PAIR_DETECTION_REASON_BONDING_CURVE_VS_QUOTE_MINT_DISAGREE,
    PAIR_DETECTION_REASON_PROVIDER_INTERNAL_INCONSISTENT,
    PAIR_DETECTION_REASON_NO_EVIDENCE,
    PAIR_DETECTION_REASON_MALFORMED_QUOTE_MINT,
)


# ---------------------------------------------------------------------------
# Known SPL mint constants
# ---------------------------------------------------------------------------


# Wrapped SOL SPL token mint (canonical mainnet). Exact-match only.
KNOWN_WRAPPED_SOL_MINT: str = (
    "So11111111111111111111111111111111111111112"
)

# Mainnet USDC SPL token mint (canonical). Exact-match only.
KNOWN_USDC_MINT: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


KNOWN_QUOTE_MINT_TO_ASSET: Mapping[str, str] = {
    KNOWN_WRAPPED_SOL_MINT: QUOTE_ASSET_SOL,
    KNOWN_USDC_MINT: QUOTE_ASSET_USDC,
}


# ---------------------------------------------------------------------------
# Public lookup helpers
# ---------------------------------------------------------------------------


def classify_known_quote_mint(quote_mint: str) -> str:
    """Return the closed-set ``QUOTE_ASSET`` token for ``quote_mint``.

    Matching is exact. An unknown / unrecognized string returns
    ``QUOTE_ASSET_UNKNOWN``; the caller must NOT default to SOL for
    an unknown quote-mint string.
    """
    if not isinstance(quote_mint, str) or quote_mint == "":
        return QUOTE_ASSET_UNKNOWN
    return KNOWN_QUOTE_MINT_TO_ASSET.get(
        quote_mint, QUOTE_ASSET_UNKNOWN
    )


def pair_type_for_quote_asset(quote_asset: str) -> str:
    """Return the canonical Pump pair-type for ``quote_asset``."""
    if quote_asset == QUOTE_ASSET_SOL:
        return PAIR_TYPE_PUMP_SOL
    if quote_asset == QUOTE_ASSET_USDC:
        return PAIR_TYPE_PUMP_USDC
    return PAIR_TYPE_UNKNOWN


def bonding_curve_version_for_quote_asset(quote_asset: str) -> str:
    """Return the canonical bonding-curve version for ``quote_asset``."""
    if quote_asset == QUOTE_ASSET_SOL:
        return BONDING_CURVE_VERSION_SOL_LEGACY
    if quote_asset == QUOTE_ASSET_USDC:
        return BONDING_CURVE_VERSION_USDC_FIXED
    return BONDING_CURVE_VERSION_UNKNOWN
