"""Stage 30.1 tier decision projector tests.

Covers the deterministic decision precedence: migration status,
ATH record presence, ATH since-migration status, ATH status,
drawdown missing, drawdown malformed, and the band classification
with intentional gaps. Also covers boundary table, signed inputs,
no-rounding pins, malformed-decimal vocabulary, identifier
sanitization, and caller-shape error paths.

Discipline: no env reads, no network, no Discord, no provider
calls. Stdlib + pytest only.
"""

from __future__ import annotations

from typing import Optional

import pytest

from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_OK,
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_SOURCE_ERROR,
    MIGRATION_STATUS_UNSUPPORTED_PAIR,
    MIGRATION_STATUS_UNTRUSTED,
    MigrationContextRecord,
    STAGE27_4_MIGRATION_SCHEMA_VERSION,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_REASON_OK,
    ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_SINCE_MIGRATION_STATUS_UNKNOWN,
    ATH_STATUS_NOT_APPLICABLE,
    ATH_STATUS_PRESENT,
    ATH_STATUS_SOURCE_ERROR,
    ATH_STATUS_STALE,
    ATH_STATUS_UNAVAILABLE,
    ATH_STATUS_UNSUPPORTED_PAIR,
    ATH_UNIT_SOL,
    AthContextRecord,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
)
from PHX2.stage30.tier_decision_models import (
    BASIS_MC,
    BASIS_PRICE,
    BASIS_VALUES,
    STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
    Stage30_1TierDecisionError,
    TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION,
    TIER_REASON_NA_MIGRATION_MISSING,
    TIER_REASON_NA_MIGRATION_SOURCE_ERROR,
    TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR,
    TIER_REASON_NA_MIGRATION_UNTRUSTED,
    TIER_REASON_TIER_1_IN_BAND,
    TIER_REASON_TIER_2_IN_BAND,
    TIER_REASON_TIER_3_IN_BAND,
    TIER_REASON_UNKNOWN_ATH_NOT_PRESENT,
    TIER_REASON_UNKNOWN_BELOW_TIER_1,
    TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED,
    TIER_REASON_UNKNOWN_DRAWDOWN_MISSING,
    TIER_REASON_UNKNOWN_GRAVEYARD,
    TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
    TIER_REASON_UNKNOWN_IN_GAP_T2_T3,
    TIER_REASON_VALUES,
    TIER_TOKEN_TIER_1,
    TIER_TOKEN_TIER_2,
    TIER_TOKEN_TIER_3,
    TIER_TOKEN_TIER_NOT_APPLICABLE,
    TIER_TOKEN_TIER_UNKNOWN,
    TIER_TOKEN_VALUES,
    TierDecisionRecord,
)
from PHX2.stage30.tier_decision_projector import decide_tier


# Real Solana wrapped-SOL mint (safe-shape, length 43, base58).
_SAFE_MINT: str = "So11111111111111111111111111111111111111112"
_SAFE_CREATED_AT: str = "2026-05-27T12:00:00Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ath_record(
    *,
    drawdown_from_ath: Optional[str] = "0.55",
    ath_status: str = ATH_STATUS_PRESENT,
    ath_since_migration_status: str = (
        ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
    ),
) -> AthContextRecord:
    return AthContextRecord(
        token_mint=_SAFE_MINT,
        pair_type="POOL_PUMPSWAP",
        quote_asset="QUOTE_SOL",
        ath_value="1.0",
        ath_unit=ATH_UNIT_SOL,
        ath_source="test",
        ath_observed_at_utc="2026-05-27T00:00:00Z",
        ath_since_migration_status=ath_since_migration_status,
        drawdown_from_ath=drawdown_from_ath,
        drawdown_unit=ATH_UNIT_SOL,
        drawdown_basis=DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        ath_status=ath_status,
        ath_reason=ATH_REASON_OK,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _make_migration_record(
    *,
    migration_status: str = MIGRATION_STATUS_PRESENT,
) -> MigrationContextRecord:
    return MigrationContextRecord(
        token_mint=_SAFE_MINT,
        pair_type="POOL_PUMPSWAP",
        quote_asset="QUOTE_SOL",
        migration_event_id="evt-xyz",
        migration_timestamp_utc="2026-05-26T00:00:00Z",
        migration_source=MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        migration_status=migration_status,
        migration_reason=MIGRATION_REASON_OK,
        age_since_migration_seconds=86400,
        observed_at_utc="2026-05-27T00:00:00Z",
        source_event_ref=None,
        raw_capture_ref=None,
        schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


_MISSING = object()


def _decide_with(
    *,
    drawdown_from_ath: Optional[str] = "0.55",
    ath_status: str = ATH_STATUS_PRESENT,
    ath_since_migration_status: str = (
        ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
    ),
    migration_status: str = MIGRATION_STATUS_PRESENT,
    ath_record: object = _MISSING,
    migration_record: object = _MISSING,
    basis: str = BASIS_PRICE,
    created_at_utc: str = _SAFE_CREATED_AT,
    ping_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    session_id: Optional[str] = None,
    mint: Optional[str] = None,
) -> TierDecisionRecord:
    if ath_record is _MISSING:
        ath_record = _make_ath_record(
            drawdown_from_ath=drawdown_from_ath,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
        )
    if migration_record is _MISSING:
        migration_record = _make_migration_record(
            migration_status=migration_status,
        )
    return decide_tier(
        ath_record=ath_record,  # type: ignore[arg-type]
        migration_record=migration_record,  # type: ignore[arg-type]
        basis=basis,
        created_at_utc=created_at_utc,
        ping_id=ping_id,
        candidate_id=candidate_id,
        session_id=session_id,
        mint=mint,
    )


# ---------------------------------------------------------------------------
# Boundary table (10 boundary drop values)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "drawdown,expected_token,expected_reason",
    [
        (
            "0.499999",
            TIER_TOKEN_TIER_UNKNOWN,
            TIER_REASON_UNKNOWN_BELOW_TIER_1,
        ),
        ("0.50", TIER_TOKEN_TIER_1, TIER_REASON_TIER_1_IN_BAND),
        ("0.60", TIER_TOKEN_TIER_1, TIER_REASON_TIER_1_IN_BAND),
        (
            "0.600001",
            TIER_TOKEN_TIER_UNKNOWN,
            TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
        ),
        ("0.62", TIER_TOKEN_TIER_2, TIER_REASON_TIER_2_IN_BAND),
        ("0.80", TIER_TOKEN_TIER_2, TIER_REASON_TIER_2_IN_BAND),
        (
            "0.800001",
            TIER_TOKEN_TIER_UNKNOWN,
            TIER_REASON_UNKNOWN_IN_GAP_T2_T3,
        ),
        ("0.82", TIER_TOKEN_TIER_3, TIER_REASON_TIER_3_IN_BAND),
        ("0.95", TIER_TOKEN_TIER_3, TIER_REASON_TIER_3_IN_BAND),
        (
            "0.950001",
            TIER_TOKEN_TIER_UNKNOWN,
            TIER_REASON_UNKNOWN_GRAVEYARD,
        ),
    ],
)
def test_boundary_table(
    drawdown: str, expected_token: str, expected_reason: str
) -> None:
    rec = _decide_with(drawdown_from_ath=drawdown)
    assert rec.tier_token == expected_token, (
        f"drawdown={drawdown!r}: expected {expected_token!r}, "
        f"got {rec.tier_token!r}"
    )
    assert rec.tier_reason == expected_reason


# ---------------------------------------------------------------------------
# Signed inputs (drop = abs(drawdown_from_ath))
# ---------------------------------------------------------------------------


def test_signed_minus_0_50_is_tier_1() -> None:
    rec = _decide_with(drawdown_from_ath="-0.50")
    assert rec.tier_token == TIER_TOKEN_TIER_1
    assert rec.tier_reason == TIER_REASON_TIER_1_IN_BAND


def test_signed_minus_0_8195_is_gap_t2_t3() -> None:
    # abs(-0.8195) = 0.8195, which falls in the 0.80..0.82 gap.
    rec = _decide_with(drawdown_from_ath="-0.8195")
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_IN_GAP_T2_T3


def test_drop_positive_is_canonical_unsigned() -> None:
    rec = _decide_with(drawdown_from_ath="-0.50")
    assert rec.drop_positive == "0.50"


def test_drop_positive_preserves_input_precision() -> None:
    rec = _decide_with(drawdown_from_ath="0.55")
    assert rec.drop_positive == "0.55"


# ---------------------------------------------------------------------------
# No-rounding pins (Decimal-exact, never float)
# ---------------------------------------------------------------------------


def test_no_rounding_0_6000000000000001_is_gap_not_tier_1() -> None:
    rec = _decide_with(drawdown_from_ath="0.6000000000000001")
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_IN_GAP_T1_T2


def test_no_rounding_0_8000000000000001_is_gap_not_tier_2() -> None:
    rec = _decide_with(drawdown_from_ath="0.8000000000000001")
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_IN_GAP_T2_T3


def test_no_rounding_many_nines_remains_in_tier_1() -> None:
    # 0.5999999999999999 (sixteen nines) is still < 0.60 -> Tier 1.
    rec = _decide_with(drawdown_from_ath="0.5999999999999999")
    assert rec.tier_token == TIER_TOKEN_TIER_1
    assert rec.tier_reason == TIER_REASON_TIER_1_IN_BAND


def test_no_rounding_0_5999_is_tier_1() -> None:
    rec = _decide_with(drawdown_from_ath="0.5999")
    assert rec.tier_token == TIER_TOKEN_TIER_1


def test_no_rounding_0_6199999999999999_is_gap() -> None:
    rec = _decide_with(drawdown_from_ath="0.6199999999999999")
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_IN_GAP_T1_T2


def test_no_rounding_0_8199999999999999_is_gap() -> None:
    rec = _decide_with(drawdown_from_ath="0.8199999999999999")
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_IN_GAP_T2_T3


def test_no_rounding_0_9500000000000001_is_graveyard() -> None:
    rec = _decide_with(drawdown_from_ath="0.9500000000000001")
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_GRAVEYARD


# ---------------------------------------------------------------------------
# Malformed decimals (strict regex ^-?\d+(\.\d+)?$)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_drawdown",
    [
        "+0.50",
        "50%",
        ".5",
        "5.",
        "0.5e0",
        "1E2",
        "NaN",
        "Infinity",
        "-Infinity",
        "",
        " 0.50",
        "0.50 ",
        " 0.50 ",
        "abc",
        "0.5.0",
        "--0.5",
        "0x50",
        "0,50",
    ],
)
def test_malformed_drawdown_classifies_as_malformed(
    bad_drawdown: str,
) -> None:
    rec = _decide_with(drawdown_from_ath=bad_drawdown)
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED


@pytest.mark.parametrize(
    "non_str",
    [0, 0.0, 50, True, False, [], (), {}, object()],
)
def test_non_string_drawdown_classifies_as_malformed(
    non_str: object,
) -> None:
    ath = _make_ath_record(drawdown_from_ath="0.55")
    ath = ath._replace(drawdown_from_ath=non_str)  # type: ignore[arg-type]
    rec = decide_tier(
        ath_record=ath,
        migration_record=_make_migration_record(),
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_CREATED_AT,
    )
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED


# ---------------------------------------------------------------------------
# Missing drawdown
# ---------------------------------------------------------------------------


def test_drawdown_none_classifies_as_missing() -> None:
    rec = _decide_with(drawdown_from_ath=None)
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_DRAWDOWN_MISSING
    assert rec.drawdown_from_ath_raw is None
    assert rec.drop_positive is None


# ---------------------------------------------------------------------------
# Migration safety statuses (with valid ATH + drawdown)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,expected_reason",
    [
        (
            MIGRATION_STATUS_MISSING,
            TIER_REASON_NA_MIGRATION_MISSING,
        ),
        (
            MIGRATION_STATUS_UNTRUSTED,
            TIER_REASON_NA_MIGRATION_UNTRUSTED,
        ),
        (
            MIGRATION_STATUS_UNSUPPORTED_PAIR,
            TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR,
        ),
        (
            MIGRATION_STATUS_SOURCE_ERROR,
            TIER_REASON_NA_MIGRATION_SOURCE_ERROR,
        ),
    ],
)
def test_migration_not_present_returns_tier_not_applicable(
    status: str, expected_reason: str
) -> None:
    rec = _decide_with(
        migration_status=status, drawdown_from_ath="0.55"
    )
    assert rec.tier_token == TIER_TOKEN_TIER_NOT_APPLICABLE
    assert rec.tier_reason == expected_reason
    assert rec.migration_status == status


def test_migration_record_none_returns_tier_not_applicable_missing() -> (
    None
):
    rec = _decide_with(
        migration_record=None, drawdown_from_ath="0.55"
    )
    assert rec.tier_token == TIER_TOKEN_TIER_NOT_APPLICABLE
    assert rec.tier_reason == TIER_REASON_NA_MIGRATION_MISSING
    assert rec.migration_status == MIGRATION_STATUS_MISSING


def test_migration_takes_precedence_over_ath_none() -> None:
    # Both migration MISSING and ath_record None: migration wins.
    rec = _decide_with(
        migration_status=MIGRATION_STATUS_MISSING,
        ath_record=None,
    )
    assert rec.tier_token == TIER_TOKEN_TIER_NOT_APPLICABLE
    assert rec.tier_reason == TIER_REASON_NA_MIGRATION_MISSING


def test_migration_takes_precedence_over_ath_may_include_pre_migration() -> (
    None
):
    # Both migration MISSING and ATH may-include-pre-migration:
    # migration wins (Tier NA / NA_MIGRATION_MISSING).
    rec = _decide_with(
        migration_status=MIGRATION_STATUS_MISSING,
        ath_since_migration_status=(
            ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
        ),
    )
    assert rec.tier_token == TIER_TOKEN_TIER_NOT_APPLICABLE
    assert rec.tier_reason == TIER_REASON_NA_MIGRATION_MISSING


# ---------------------------------------------------------------------------
# ATH None vs MAY_INCLUDE_PRE_MIGRATION distinction
# ---------------------------------------------------------------------------


def test_ath_record_none_with_migration_present_is_tier_unknown() -> (
    None
):
    rec = _decide_with(ath_record=None)
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_ATH_NOT_PRESENT
    # Not the NA reason.
    assert (
        rec.tier_reason
        != TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION
    )


def test_ath_may_include_pre_migration_is_tier_not_applicable() -> (
    None
):
    rec = _decide_with(
        ath_since_migration_status=(
            ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
        ),
        drawdown_from_ath="0.55",
    )
    assert rec.tier_token == TIER_TOKEN_TIER_NOT_APPLICABLE
    assert (
        rec.tier_reason
        == TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION
    )


def test_ath_since_migration_unknown_is_not_tier_na() -> None:
    # ATH_SINCE_MIGRATION_STATUS_UNKNOWN is not MAY_INCLUDE_PRE_MIGRATION,
    # so the projector does not force Tier Not Applicable on that token
    # alone. With a valid drawdown, classification proceeds.
    rec = _decide_with(
        ath_since_migration_status=(
            ATH_SINCE_MIGRATION_STATUS_UNKNOWN
        ),
        drawdown_from_ath="0.55",
    )
    assert rec.tier_token == TIER_TOKEN_TIER_1
    assert rec.tier_reason == TIER_REASON_TIER_1_IN_BAND


@pytest.mark.parametrize(
    "degraded_ath_status",
    [
        ATH_STATUS_STALE,
        ATH_STATUS_UNAVAILABLE,
        ATH_STATUS_NOT_APPLICABLE,
        ATH_STATUS_UNSUPPORTED_PAIR,
        ATH_STATUS_SOURCE_ERROR,
    ],
)
def test_ath_status_degraded_is_tier_unknown_not_present(
    degraded_ath_status: str,
) -> None:
    rec = _decide_with(
        ath_status=degraded_ath_status, drawdown_from_ath="0.55"
    )
    assert rec.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert rec.tier_reason == TIER_REASON_UNKNOWN_ATH_NOT_PRESENT


# ---------------------------------------------------------------------------
# Closed-set output validity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "drawdown",
    [
        "0.55",
        "0.99",
        "-0.55",
        "0.5",
        "+0.5",
        "abc",
        "",
        None,
    ],
)
def test_output_tokens_always_in_closed_sets(
    drawdown: Optional[str],
) -> None:
    rec = _decide_with(drawdown_from_ath=drawdown)
    assert rec.tier_token in TIER_TOKEN_VALUES
    assert rec.tier_reason in TIER_REASON_VALUES
    assert rec.basis in BASIS_VALUES


def test_record_has_locked_schema_version() -> None:
    rec = _decide_with()
    assert (
        rec.schema_version
        == STAGE30_1_TIER_DECISION_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# Caller-shape error paths
# ---------------------------------------------------------------------------


def test_invalid_basis_raises() -> None:
    with pytest.raises(Stage30_1TierDecisionError) as exc:
        decide_tier(
            ath_record=_make_ath_record(),
            migration_record=_make_migration_record(),
            basis="invalid-basis",
            created_at_utc=_SAFE_CREATED_AT,
        )
    assert exc.value.reason == "BASIS_INVALID"


def test_empty_basis_raises() -> None:
    with pytest.raises(Stage30_1TierDecisionError) as exc:
        decide_tier(
            ath_record=_make_ath_record(),
            migration_record=_make_migration_record(),
            basis="",
            created_at_utc=_SAFE_CREATED_AT,
        )
    assert exc.value.reason == "BASIS_INVALID"


def test_non_string_basis_raises() -> None:
    with pytest.raises(Stage30_1TierDecisionError) as exc:
        decide_tier(
            ath_record=_make_ath_record(),
            migration_record=_make_migration_record(),
            basis=42,  # type: ignore[arg-type]
            created_at_utc=_SAFE_CREATED_AT,
        )
    assert exc.value.reason == "BASIS_INVALID"


def test_invalid_created_at_utc_raises() -> None:
    with pytest.raises(Stage30_1TierDecisionError) as exc:
        decide_tier(
            ath_record=_make_ath_record(),
            migration_record=_make_migration_record(),
            basis=BASIS_PRICE,
            created_at_utc="not-an-iso-string",
        )
    assert exc.value.reason == "CREATED_AT_UTC_NOT_SAFE_ISO8601"


def test_created_at_utc_with_url_substring_raises() -> None:
    with pytest.raises(Stage30_1TierDecisionError):
        decide_tier(
            ath_record=_make_ath_record(),
            migration_record=_make_migration_record(),
            basis=BASIS_PRICE,
            created_at_utc="2026-05-27Tdiscord.com",
        )


def test_invalid_ath_record_type_raises() -> None:
    with pytest.raises(Stage30_1TierDecisionError) as exc:
        decide_tier(
            ath_record="not-a-record",  # type: ignore[arg-type]
            migration_record=_make_migration_record(),
            basis=BASIS_PRICE,
            created_at_utc=_SAFE_CREATED_AT,
        )
    assert exc.value.reason == "ATH_RECORD_INVALID_TYPE"


def test_invalid_migration_record_type_raises() -> None:
    with pytest.raises(Stage30_1TierDecisionError) as exc:
        decide_tier(
            ath_record=_make_ath_record(),
            migration_record="not-a-record",  # type: ignore[arg-type]
            basis=BASIS_PRICE,
            created_at_utc=_SAFE_CREATED_AT,
        )
    assert exc.value.reason == "MIGRATION_RECORD_INVALID_TYPE"


def test_created_at_utc_iso_with_millis_accepted() -> None:
    rec = _decide_with(created_at_utc="2026-05-27T12:00:00.123Z")
    assert rec.created_at_utc == "2026-05-27T12:00:00.123Z"


# ---------------------------------------------------------------------------
# Basis tokens
# ---------------------------------------------------------------------------


def test_basis_price_echoed_on_record() -> None:
    rec = _decide_with(basis=BASIS_PRICE)
    assert rec.basis == "price-basis"


def test_basis_mc_accepted_but_no_mc_fetched() -> None:
    # Stage 30.1 may accept "mc-basis" but it does NOT fetch MC;
    # it classifies from the supplied drawdown_from_ath verbatim.
    rec = _decide_with(basis=BASIS_MC, drawdown_from_ath="0.55")
    assert rec.basis == "mc-basis"
    assert rec.tier_token == TIER_TOKEN_TIER_1


# ---------------------------------------------------------------------------
# Identifier sanitization
# ---------------------------------------------------------------------------


def test_safe_identifiers_echoed_on_record() -> None:
    rec = _decide_with(
        ping_id="ping-001",
        candidate_id="cand-abc.123",
        session_id="sess_xyz",
        mint=_SAFE_MINT,
    )
    assert rec.ping_id == "ping-001"
    assert rec.candidate_id == "cand-abc.123"
    assert rec.session_id == "sess_xyz"
    assert rec.mint == _SAFE_MINT


@pytest.mark.parametrize(
    "unsafe_ident",
    [
        "ping with space",
        "ping/slash",
        "ping\\backslash",
        "ping=equals",
        "ping:colon",
        "https://discord.com/ping",
        "ping\nnewline",
        "ping\ttab",
        "x" * 65,
        "",
    ],
)
def test_unsafe_identifier_redacted_to_none(unsafe_ident: str) -> None:
    rec = _decide_with(ping_id=unsafe_ident)
    assert rec.ping_id is None


@pytest.mark.parametrize(
    "non_str_ident",
    [12345, 0, True, [], {}, object()],
)
def test_non_string_identifier_redacted_to_none(
    non_str_ident: object,
) -> None:
    rec = _decide_with(ping_id=non_str_ident)  # type: ignore[arg-type]
    assert rec.ping_id is None


def test_unsafe_mint_redacted_to_none() -> None:
    rec = _decide_with(mint="https://discord.com/foo")
    assert rec.mint is None


def test_short_mint_redacted_to_none() -> None:
    rec = _decide_with(mint="short")
    assert rec.mint is None


def test_too_long_mint_redacted_to_none() -> None:
    rec = _decide_with(mint="a" * 100)
    assert rec.mint is None


def test_mint_with_non_base58_char_redacted_to_none() -> None:
    # '0' is NOT in the base58 alphabet (Solana base58 excludes 0/O/I/l).
    bad_mint = "0" * 43
    rec = _decide_with(mint=bad_mint)
    assert rec.mint is None


# ---------------------------------------------------------------------------
# Pure-function / determinism
# ---------------------------------------------------------------------------


def test_two_identical_calls_produce_equal_records() -> None:
    ath = _make_ath_record(drawdown_from_ath="0.75")
    mig = _make_migration_record()
    rec_a = decide_tier(
        ath_record=ath,
        migration_record=mig,
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_CREATED_AT,
        ping_id="ping-001",
        candidate_id="cand-abc",
        session_id="sess-xyz",
        mint=_SAFE_MINT,
    )
    rec_b = decide_tier(
        ath_record=ath,
        migration_record=mig,
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_CREATED_AT,
        ping_id="ping-001",
        candidate_id="cand-abc",
        session_id="sess-xyz",
        mint=_SAFE_MINT,
    )
    assert rec_a == rec_b


def test_created_at_utc_echoed_verbatim() -> None:
    rec = _decide_with(created_at_utc="2026-12-31T23:59:59Z")
    assert rec.created_at_utc == "2026-12-31T23:59:59Z"


# ---------------------------------------------------------------------------
# Drawdown raw echo behavior
# ---------------------------------------------------------------------------


def test_drawdown_raw_echoed_when_safe_shape() -> None:
    rec = _decide_with(drawdown_from_ath="0.55")
    assert rec.drawdown_from_ath_raw == "0.55"


def test_drawdown_raw_echoed_when_malformed_but_safe_shape() -> None:
    # "+0.50" is structurally safe-shape (digits + '+' + '.') but
    # the strict regex rejects the leading '+'. The echo preserves
    # the original input so the operator can audit.
    rec = _decide_with(drawdown_from_ath="+0.50")
    assert rec.drawdown_from_ath_raw == "+0.50"
    assert rec.tier_reason == TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED


def test_drawdown_raw_redacted_when_unsafe_chars() -> None:
    rec = _decide_with(drawdown_from_ath="50%")
    assert rec.drawdown_from_ath_raw is None
    assert rec.tier_reason == TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED


def test_drawdown_raw_redacted_for_url_like_input() -> None:
    rec = _decide_with(
        drawdown_from_ath="https://discord.com/abc"
    )
    assert rec.drawdown_from_ath_raw is None
    assert rec.tier_reason == TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED


def test_drop_positive_none_when_short_circuited_by_safety() -> None:
    # Migration MISSING short-circuits before drawdown parse,
    # so drop_positive remains None even with a valid drawdown.
    rec = _decide_with(
        migration_status=MIGRATION_STATUS_MISSING,
        drawdown_from_ath="0.55",
    )
    assert rec.drop_positive is None


def test_drop_positive_set_when_band_classified() -> None:
    rec = _decide_with(drawdown_from_ath="0.55")
    assert rec.drop_positive == "0.55"


# ---------------------------------------------------------------------------
# Closed-set echoed inputs when records absent
# ---------------------------------------------------------------------------


def test_ath_status_fallback_when_record_none() -> None:
    rec = _decide_with(ath_record=None)
    assert rec.ath_status == ATH_STATUS_UNAVAILABLE
    assert (
        rec.ath_since_migration_status
        == ATH_SINCE_MIGRATION_STATUS_UNKNOWN
    )


def test_migration_status_fallback_when_record_none() -> None:
    rec = _decide_with(migration_record=None)
    assert rec.migration_status == MIGRATION_STATUS_MISSING


def test_both_records_none() -> None:
    rec = _decide_with(ath_record=None, migration_record=None)
    # Migration check fires first.
    assert rec.tier_token == TIER_TOKEN_TIER_NOT_APPLICABLE
    assert rec.tier_reason == TIER_REASON_NA_MIGRATION_MISSING
    assert rec.ath_status == ATH_STATUS_UNAVAILABLE
    assert rec.migration_status == MIGRATION_STATUS_MISSING
