"""Stage 27.2 pair-detection constants tests.

Pins:

  * Every closed-set vocabulary (quote_asset / pair_type /
    bonding_curve_version / pair_detection_status /
    pair_detection_confidence / pair_detection_source /
    live_policy / calibration_lane / pair_detection_reason) is the
    exact locked tuple.
  * Known SOL / USDC quote-mint constants are the canonical
    mainnet SPL mint strings; matching is exact.
  * Stage 27.2 version axes are pinned.
  * ``classify_known_quote_mint`` returns SOL / USDC for exact
    matches, UNKNOWN otherwise; an empty / missing / non-string
    quote-mint is NEVER promoted to SOL.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import pair_detection_constants as c


# ---------------------------------------------------------------------------
# Closed-set tuples
# ---------------------------------------------------------------------------


def test_quote_asset_values_are_locked_tuple():
    assert c.QUOTE_ASSET_VALUES == ("SOL", "USDC", "UNKNOWN")


def test_quote_asset_token_constants():
    assert c.QUOTE_ASSET_SOL == "SOL"
    assert c.QUOTE_ASSET_USDC == "USDC"
    assert c.QUOTE_ASSET_UNKNOWN == "UNKNOWN"


def test_pair_type_values_are_locked_tuple():
    assert c.PAIR_TYPE_VALUES == (
        "PUMP_SOL",
        "PUMP_USDC",
        "UNKNOWN",
    )


def test_pair_type_token_constants():
    assert c.PAIR_TYPE_PUMP_SOL == "PUMP_SOL"
    assert c.PAIR_TYPE_PUMP_USDC == "PUMP_USDC"
    assert c.PAIR_TYPE_UNKNOWN == "UNKNOWN"


def test_bonding_curve_version_values_are_locked_tuple():
    assert c.BONDING_CURVE_VERSION_VALUES == (
        "SOL_LEGACY",
        "USDC_FIXED",
        "UNKNOWN",
    )


def test_bonding_curve_version_token_constants():
    assert c.BONDING_CURVE_VERSION_SOL_LEGACY == "SOL_LEGACY"
    assert c.BONDING_CURVE_VERSION_USDC_FIXED == "USDC_FIXED"
    assert c.BONDING_CURVE_VERSION_UNKNOWN == "UNKNOWN"


def test_pair_detection_status_values_are_locked_tuple():
    assert c.PAIR_DETECTION_STATUS_VALUES == (
        "CONFIRMED",
        "PROVIDER_ONLY",
        "DISAGREE",
        "UNRESOLVED",
    )


def test_pair_detection_confidence_values_are_locked_tuple():
    assert c.PAIR_DETECTION_CONFIDENCE_VALUES == (
        "HIGH",
        "MEDIUM",
        "LOW",
        "NONE",
    )


def test_pair_detection_source_values_are_locked_tuple():
    assert c.PAIR_DETECTION_SOURCE_VALUES == (
        "POOL_QUOTE_MINT",
        "BONDING_CURVE_METADATA",
        "MIGRATION_EVENT",
        "PROVIDER_PAYLOAD",
        "KNOWN_MINT_FALLBACK",
    )


def test_source_strength_tiers_partition_full_set():
    """Every source token belongs to exactly one strength tier."""
    union = (
        set(c.PAIR_DETECTION_SOURCES_STRONG)
        | set(c.PAIR_DETECTION_SOURCES_MIDDLE)
        | set(c.PAIR_DETECTION_SOURCES_WEAK)
    )
    assert union == set(c.PAIR_DETECTION_SOURCE_VALUES)
    # Tiers are disjoint.
    assert (
        set(c.PAIR_DETECTION_SOURCES_STRONG)
        & set(c.PAIR_DETECTION_SOURCES_MIDDLE)
        == set()
    )
    assert (
        set(c.PAIR_DETECTION_SOURCES_STRONG)
        & set(c.PAIR_DETECTION_SOURCES_WEAK)
        == set()
    )
    assert (
        set(c.PAIR_DETECTION_SOURCES_MIDDLE)
        & set(c.PAIR_DETECTION_SOURCES_WEAK)
        == set()
    )


def test_source_strong_tier_contains_pool_and_bonding_curve():
    assert set(c.PAIR_DETECTION_SOURCES_STRONG) == {
        "POOL_QUOTE_MINT",
        "BONDING_CURVE_METADATA",
    }


def test_source_middle_tier_contains_migration_event():
    assert set(c.PAIR_DETECTION_SOURCES_MIDDLE) == {
        "MIGRATION_EVENT",
    }


def test_source_weak_tier_contains_provider_and_known_mint_fallback():
    assert set(c.PAIR_DETECTION_SOURCES_WEAK) == {
        "PROVIDER_PAYLOAD",
        "KNOWN_MINT_FALLBACK",
    }


def test_live_policy_values_are_locked_tuple():
    assert c.LIVE_POLICY_VALUES == (
        "LIVE_ALLOWED",
        "LIVE_SUPPRESS_UNKNOWN",
        "LIVE_SUPPRESS_DISAGREE",
        "DRY_RUN_ONLY",
    )


def test_calibration_lane_values_are_locked_tuple():
    assert c.CALIBRATION_LANE_VALUES == (
        "EXISTING_SOL_LANE",
        "USDC_OBSERVE_ONLY",
        "UNKNOWN_PAIR_OBSERVE_ONLY",
        "DISAGREE_PAIR_OBSERVE_ONLY",
    )


def test_pair_detection_reason_values_are_locked_tuple():
    assert c.PAIR_DETECTION_REASON_VALUES == (
        "CONFIRMED_AGREEMENT",
        "SINGLE_STRONG_SOURCE",
        "PROVIDER_ONLY_EVIDENCE",
        "MIGRATION_HINT_ONLY",
        "STRONG_SOURCE_DISAGREE",
        "QUOTE_MINT_VS_PROVIDER_DISAGREE",
        "BONDING_CURVE_VS_QUOTE_MINT_DISAGREE",
        "PROVIDER_INTERNAL_INCONSISTENT",
        "NO_EVIDENCE",
        "MALFORMED_QUOTE_MINT",
    )


# ---------------------------------------------------------------------------
# Stage 27.2 version axes
# ---------------------------------------------------------------------------


def test_stage_27_2_version_axes():
    assert c.STAGE27_2_MINOR_VERSION == "27.2"
    assert c.STAGE27_2_SCHEMA_VERSION == "stage27_v0_pair_detection"


# ---------------------------------------------------------------------------
# Known SPL mint constants
# ---------------------------------------------------------------------------


def test_known_wrapped_sol_mint_is_canonical_string():
    # Canonical mainnet wrapped-SOL SPL token mint. Pinned verbatim
    # so a future rename can not silently move a different mint
    # into the SOL slot.
    assert c.KNOWN_WRAPPED_SOL_MINT == (
        "So11111111111111111111111111111111111111112"
    )


def test_known_usdc_mint_is_canonical_string():
    # Canonical mainnet USDC SPL token mint. Pinned verbatim.
    assert c.KNOWN_USDC_MINT == (
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    )


def test_known_sol_and_usdc_mints_are_distinct():
    assert c.KNOWN_WRAPPED_SOL_MINT != c.KNOWN_USDC_MINT


def test_known_quote_mint_map_only_contains_sol_and_usdc():
    assert set(c.KNOWN_QUOTE_MINT_TO_ASSET.keys()) == {
        c.KNOWN_WRAPPED_SOL_MINT,
        c.KNOWN_USDC_MINT,
    }
    assert (
        c.KNOWN_QUOTE_MINT_TO_ASSET[c.KNOWN_WRAPPED_SOL_MINT]
        == c.QUOTE_ASSET_SOL
    )
    assert (
        c.KNOWN_QUOTE_MINT_TO_ASSET[c.KNOWN_USDC_MINT]
        == c.QUOTE_ASSET_USDC
    )


# ---------------------------------------------------------------------------
# classify_known_quote_mint
# ---------------------------------------------------------------------------


def test_classify_known_quote_mint_returns_sol_for_wrapped_sol_mint():
    assert (
        c.classify_known_quote_mint(c.KNOWN_WRAPPED_SOL_MINT)
        == c.QUOTE_ASSET_SOL
    )


def test_classify_known_quote_mint_returns_usdc_for_usdc_mint():
    assert (
        c.classify_known_quote_mint(c.KNOWN_USDC_MINT)
        == c.QUOTE_ASSET_USDC
    )


def test_classify_known_quote_mint_returns_unknown_for_unrecognized():
    # Garbage strings -> UNKNOWN. MUST NOT promote to SOL.
    for value in (
        "garbage",
        "So11111111111111111111111111111111111111111",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1u",
        "FAKEMINTSTRINGNOTAREAL_MINT",
    ):
        assert (
            c.classify_known_quote_mint(value)
            == c.QUOTE_ASSET_UNKNOWN
        )


def test_classify_known_quote_mint_empty_string_is_unknown():
    assert c.classify_known_quote_mint("") == c.QUOTE_ASSET_UNKNOWN


def test_classify_known_quote_mint_non_string_is_unknown():
    # Defensive: malformed inputs must not crash and must not
    # default to SOL.
    assert (
        c.classify_known_quote_mint(None)  # type: ignore[arg-type]
        == c.QUOTE_ASSET_UNKNOWN
    )
    assert (
        c.classify_known_quote_mint(123)  # type: ignore[arg-type]
        == c.QUOTE_ASSET_UNKNOWN
    )
    assert (
        c.classify_known_quote_mint(
            ["So11111111111111111111111111111111111111112"]
        )  # type: ignore[arg-type]
        == c.QUOTE_ASSET_UNKNOWN
    )


def test_classify_known_quote_mint_matching_is_exact_only():
    """Trailing whitespace or case changes MUST NOT match."""
    assert (
        c.classify_known_quote_mint(c.KNOWN_WRAPPED_SOL_MINT + " ")
        == c.QUOTE_ASSET_UNKNOWN
    )
    assert (
        c.classify_known_quote_mint(
            c.KNOWN_WRAPPED_SOL_MINT.upper()
        )
        == c.QUOTE_ASSET_UNKNOWN
    )


# ---------------------------------------------------------------------------
# pair_type / bonding_curve_version per-asset helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "asset,pair_type",
    [
        ("SOL", "PUMP_SOL"),
        ("USDC", "PUMP_USDC"),
        ("UNKNOWN", "UNKNOWN"),
    ],
)
def test_pair_type_for_quote_asset(asset, pair_type):
    assert c.pair_type_for_quote_asset(asset) == pair_type


@pytest.mark.parametrize(
    "asset,bcv",
    [
        ("SOL", "SOL_LEGACY"),
        ("USDC", "USDC_FIXED"),
        ("UNKNOWN", "UNKNOWN"),
    ],
)
def test_bonding_curve_version_for_quote_asset(asset, bcv):
    assert c.bonding_curve_version_for_quote_asset(asset) == bcv
