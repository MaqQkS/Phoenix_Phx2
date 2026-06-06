"""Stage 30.1 tier-units regression tests.

Locks the audit-confirmed fix: ``decide_tier`` bands on the FRACTIONAL drop
``abs(drawdown_from_ath) / ath_value`` -- NOT on the absolute USD delta Stage
27.4 emits. Without the fix every sub-dollar (memecoin) token classified as
``Tier Unknown / UNKNOWN_BELOW_TIER_1`` because its absolute ``ATH - price``
delta is far below 0.50; with the fix a real 55 / 80 / 90 % dip on a memecoin-
scale ATH classifies Tier 1 / 2 / 3.

Also locks: existing $1-scale behavior is unchanged (absolute == fractional when
ATH == 1.0), the live-proof mint stays ``Tier Unknown`` (only ~6.72 % off ATH),
and a missing / blank / malformed / non-finite / zero / negative ``ath_value``
fails closed to ``Tier Unknown / UNKNOWN_ATH_VALUE_INVALID`` (never /0).

Discipline: no env reads, no network, no Discord, no provider calls. Stdlib +
pytest only.
"""

from __future__ import annotations

from typing import Optional

import pytest

from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_OK,
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_STATUS_PRESENT,
    MigrationContextRecord,
    STAGE27_4_MIGRATION_SCHEMA_VERSION,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_REASON_OK,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_STATUS_PRESENT,
    ATH_UNIT_USD,
    AthContextRecord,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
)
from PHX2.stage30.tier_decision_models import (
    BASIS_PRICE,
    TIER_REASON_TIER_1_IN_BAND,
    TIER_REASON_TIER_2_IN_BAND,
    TIER_REASON_TIER_3_IN_BAND,
    TIER_REASON_UNKNOWN_ATH_VALUE_INVALID,
    TIER_REASON_UNKNOWN_BELOW_TIER_1,
    TIER_REASON_UNKNOWN_GRAVEYARD,
    TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
    TIER_REASON_UNKNOWN_IN_GAP_T2_T3,
    TIER_TOKEN_TIER_1,
    TIER_TOKEN_TIER_2,
    TIER_TOKEN_TIER_3,
    TIER_TOKEN_TIER_UNKNOWN,
)
from PHX2.stage30.tier_decision_projector import decide_tier

_SAFE_MINT = "So11111111111111111111111111111111111111112"
_CREATED = "2026-06-06T12:00:00Z"


def _ath_record(
    *, ath_value: Optional[str], drawdown_from_ath: Optional[str]
) -> AthContextRecord:
    return AthContextRecord(
        token_mint=_SAFE_MINT,
        pair_type="POOL_PUMPSWAP",
        quote_asset="QUOTE_SOL",
        ath_value=ath_value,
        ath_unit=ATH_UNIT_USD,
        ath_source="regression",
        ath_observed_at_utc="2026-06-06T00:00:00Z",
        ath_since_migration_status=ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
        drawdown_from_ath=drawdown_from_ath,
        drawdown_unit=ATH_UNIT_USD,
        drawdown_basis=DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        ath_status=ATH_STATUS_PRESENT,
        ath_reason=ATH_REASON_OK,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _present_migration() -> MigrationContextRecord:
    return MigrationContextRecord(
        token_mint=_SAFE_MINT,
        pair_type="POOL_PUMPSWAP",
        quote_asset="QUOTE_SOL",
        migration_event_id="evt",
        migration_timestamp_utc="2026-06-05T00:00:00Z",
        migration_source=MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_reason=MIGRATION_REASON_OK,
        age_since_migration_seconds=86400,
        observed_at_utc="2026-06-06T00:00:00Z",
        source_event_ref=None,
        raw_capture_ref=None,
        schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def _decide(*, ath_value: Optional[str], drawdown_from_ath: Optional[str]):
    return decide_tier(
        ath_record=_ath_record(
            ath_value=ath_value, drawdown_from_ath=drawdown_from_ath
        ),
        migration_record=_present_migration(),
        basis=BASIS_PRICE,
        created_at_utc=_CREATED,
        mint=_SAFE_MINT,
    )


# ---------------------------------------------------------------------------
# 1-4. Memecoin-scale tiers (the bug cases the audit confirmed)
# ---------------------------------------------------------------------------


def test_memecoin_tier_1_fractional_0_55() -> None:
    # ATH 0.00000100, current 0.00000045 -> absolute 0.00000055, fraction 0.55.
    rec = _decide(ath_value="0.00000100", drawdown_from_ath="0.00000055")
    assert rec.tier_token == TIER_TOKEN_TIER_1
    assert rec.tier_reason == TIER_REASON_TIER_1_IN_BAND
    # The band used the fraction (0.55) internally, but drop_positive and
    # drawdown_from_ath_raw both stay the ABSOLUTE USD delta (unchanged display).
    assert rec.drop_positive == "0.00000055"
    assert rec.drawdown_from_ath_raw == "0.00000055"


def test_memecoin_tier_2_fractional_0_80() -> None:
    # ATH 0.00000100, current 0.00000020 -> absolute 0.00000080, fraction 0.80.
    rec = _decide(ath_value="0.00000100", drawdown_from_ath="0.00000080")
    assert rec.tier_token == TIER_TOKEN_TIER_2
    assert rec.tier_reason == TIER_REASON_TIER_2_IN_BAND


def test_memecoin_tier_3_fractional_0_90() -> None:
    # ATH 0.00000100, current 0.00000010 -> absolute 0.00000090, fraction 0.90.
    rec = _decide(ath_value="0.00000100", drawdown_from_ath="0.00000090")
    assert rec.tier_token == TIER_TOKEN_TIER_3
    assert rec.tier_reason == TIER_REASON_TIER_3_IN_BAND


def test_memecoin_below_tier_1_fractional_0_28() -> None:
    # ATH 0.00000100, current 0.00000072 -> absolute 0.00000028, fraction 0.28.
    rec = _decide(ath_value="0.00000100", drawdown_from_ath="0.00000028")
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_BELOW_TIER_1


# ---------------------------------------------------------------------------
# 5. Existing $1-scale behavior unchanged (absolute == fractional at ATH 1.0)
# ---------------------------------------------------------------------------


def test_dollar_scale_tier_1_unchanged() -> None:
    rec = _decide(ath_value="1.00", drawdown_from_ath="0.55")
    assert rec.tier_token == TIER_TOKEN_TIER_1
    assert rec.tier_reason == TIER_REASON_TIER_1_IN_BAND
    assert rec.drop_positive == "0.55"


# ---------------------------------------------------------------------------
# Live-proof mint stays Tier Unknown (only ~6.72% off ATH; below Tier 1)
# ---------------------------------------------------------------------------


def test_live_proof_mint_stays_tier_unknown() -> None:
    rec = _decide(
        ath_value="0.00000042789319238283876",
        drawdown_from_ath="0.00000002875133686874152",
    )
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_BELOW_TIER_1


# ---------------------------------------------------------------------------
# Band boundaries on the fraction at memecoin scale (inclusion/exclusion)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "drawdown, ath, expected_token, expected_reason",
    [
        # exact band edges (ATH 0.00000100 so fraction = drawdown / 1e-6)
        ("0.00000050", "0.00000100", TIER_TOKEN_TIER_1, TIER_REASON_TIER_1_IN_BAND),
        ("0.00000060", "0.00000100", TIER_TOKEN_TIER_1, TIER_REASON_TIER_1_IN_BAND),
        ("0.00000061", "0.00000100", TIER_TOKEN_TIER_UNKNOWN, TIER_REASON_UNKNOWN_IN_GAP_T1_T2),
        ("0.00000062", "0.00000100", TIER_TOKEN_TIER_2, TIER_REASON_TIER_2_IN_BAND),
        ("0.00000080", "0.00000100", TIER_TOKEN_TIER_2, TIER_REASON_TIER_2_IN_BAND),
        ("0.00000081", "0.00000100", TIER_TOKEN_TIER_UNKNOWN, TIER_REASON_UNKNOWN_IN_GAP_T2_T3),
        ("0.00000082", "0.00000100", TIER_TOKEN_TIER_3, TIER_REASON_TIER_3_IN_BAND),
        ("0.00000095", "0.00000100", TIER_TOKEN_TIER_3, TIER_REASON_TIER_3_IN_BAND),
        ("0.00000096", "0.00000100", TIER_TOKEN_TIER_UNKNOWN, TIER_REASON_UNKNOWN_GRAVEYARD),
    ],
)
def test_memecoin_band_boundaries(
    drawdown, ath, expected_token, expected_reason
) -> None:
    rec = _decide(ath_value=ath, drawdown_from_ath=drawdown)
    assert rec.tier_token == expected_token
    assert rec.tier_reason == expected_reason


# ---------------------------------------------------------------------------
# Codex precision-boundary probe: exact cross-multiplication, no rounded quotient
# ---------------------------------------------------------------------------


def test_codex_probe_just_below_062_is_gap_not_tier_2() -> None:
    # 1.85999999999999999999999999999 / 3 = 0.6199999...9967 (just BELOW 0.62).
    # A context-rounded quotient rounds to 0.62 and would mis-band as Tier 2;
    # exact cross-multiplication keeps it in the T1/T2 gap.
    rec = _decide(
        ath_value="3",
        drawdown_from_ath="1.85999999999999999999999999999",
    )
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_IN_GAP_T1_T2
    # drop_positive preserves the EXACT absolute drawdown; it is NOT rounded to
    # "1.860000000000000000000000000".
    assert rec.drop_positive == "1.85999999999999999999999999999"
    assert rec.drawdown_from_ath_raw == "1.85999999999999999999999999999"


def test_codex_boundary_exactly_062_is_tier_2() -> None:
    # 1.86 / 3 = 0.62 exactly -> Tier 2 (lower edge inclusive).
    rec = _decide(ath_value="3", drawdown_from_ath="1.86")
    assert rec.tier_token == TIER_TOKEN_TIER_2
    assert rec.tier_reason == TIER_REASON_TIER_2_IN_BAND


def test_codex_just_above_062_is_tier_2() -> None:
    # 1.86000000000000000000000000001 / 3 just ABOVE 0.62 -> Tier 2.
    rec = _decide(
        ath_value="3",
        drawdown_from_ath="1.86000000000000000000000000001",
    )
    assert rec.tier_token == TIER_TOKEN_TIER_2
    assert rec.tier_reason == TIER_REASON_TIER_2_IN_BAND


# ---------------------------------------------------------------------------
# 6. Invalid ATH value -> fail closed to Tier Unknown / UNKNOWN_ATH_VALUE_INVALID
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_ath_value",
    [
        None,            # missing
        "",              # blank
        "   ",           # whitespace
        "not_a_number",  # malformed
        "1.2.3",         # malformed
        "1e-6",          # scientific notation (rejected by strict pattern)
        "NaN",           # non-finite
        "Infinity",      # non-finite
        "0",             # zero -> would divide by zero
        "0.0",           # zero
        "-0.00000100",   # negative
    ],
)
def test_invalid_ath_value_fails_closed(bad_ath_value) -> None:
    rec = _decide(ath_value=bad_ath_value, drawdown_from_ath="0.00000055")
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_ATH_VALUE_INVALID
    assert rec.drop_positive is None


def test_valid_ath_value_does_not_divide_by_zero_and_classifies() -> None:
    # Sanity: a strictly-positive ath_value classifies normally (no exception).
    rec = _decide(ath_value="0.00000100", drawdown_from_ath="0.00000055")
    assert rec.tier_token == TIER_TOKEN_TIER_1
