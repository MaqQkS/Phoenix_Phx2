"""Stage 30.12 PHOENIX operator ping models tests.

Pure read-only tests over the Stage 30.12 input record shape + defaults, the
tier-band display map, the closed-set constants (schema version, body cap,
display sentinel, operator footer, WSOL quote-mint guard value), the
forbidden-field-name guard, and the closed-set error.

Discipline: no env reads, no network, no Discord, no provider calls. Stdlib +
pytest only.
"""

from __future__ import annotations

from PHX2.stage30.stage30_12_phoenix_operator_ping_models import (
    DISPLAY_UNKNOWN,
    FORBIDDEN_RECORD_FIELD_NAMES,
    PhoenixOperatorPingInput,
    STAGE30_12_BODY_CHAR_HARD_CAP,
    STAGE30_12_MINOR_VERSION,
    STAGE30_12_OPERATOR_FOOTER,
    STAGE30_12_PHOENIX_OPERATOR_PING_SCHEMA_VERSION,
    Stage30_12PhoenixOperatorPingError,
    TIER_BAND_DISPLAY_BY_TIER_TOKEN,
    TIER_BAND_DISPLAY_TIER_1,
    TIER_BAND_DISPLAY_TIER_2,
    TIER_BAND_DISPLAY_TIER_3,
    TIER_TOKEN_TIER_1,
    TIER_TOKEN_TIER_2,
    TIER_TOKEN_TIER_3,
    TIER_TOKEN_TIER_NOT_APPLICABLE,
    TIER_TOKEN_TIER_UNKNOWN,
    WSOL_QUOTE_MINT,
    is_forbidden_record_field_name,
    tier_band_display_for,
)


# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------


def test_minor_version_and_schema_version() -> None:
    assert STAGE30_12_MINOR_VERSION == "30.12"
    assert STAGE30_12_PHOENIX_OPERATOR_PING_SCHEMA_VERSION == (
        "stage30_12_v0_phoenix_operator_ping"
    )


def test_body_cap_sentinel_footer() -> None:
    assert STAGE30_12_BODY_CHAR_HARD_CAP == 1900
    assert DISPLAY_UNKNOWN == "Unknown"
    assert STAGE30_12_OPERATOR_FOOTER == "PRIVATE OPERATOR ONLY · PHX2"


def test_wsol_quote_mint_value() -> None:
    assert WSOL_QUOTE_MINT == "So11111111111111111111111111111111111111112"


def test_tier_tokens() -> None:
    assert TIER_TOKEN_TIER_1 == "Tier 1"
    assert TIER_TOKEN_TIER_2 == "Tier 2"
    assert TIER_TOKEN_TIER_3 == "Tier 3"
    assert TIER_TOKEN_TIER_UNKNOWN == "Tier Unknown"
    assert TIER_TOKEN_TIER_NOT_APPLICABLE == "Tier Not Applicable"


# ---------------------------------------------------------------------------
# 2. Tier band display map
# ---------------------------------------------------------------------------


def test_tier_band_display_constants() -> None:
    assert TIER_BAND_DISPLAY_TIER_1 == "50%–60%"
    assert TIER_BAND_DISPLAY_TIER_2 == "62%–80%"
    assert TIER_BAND_DISPLAY_TIER_3 == "82%–95%"


def test_tier_band_display_map_keys_are_only_the_three_tiers() -> None:
    assert set(TIER_BAND_DISPLAY_BY_TIER_TOKEN.keys()) == {
        TIER_TOKEN_TIER_1,
        TIER_TOKEN_TIER_2,
        TIER_TOKEN_TIER_3,
    }


def test_tier_band_display_for_maps_each_tier() -> None:
    assert tier_band_display_for(TIER_TOKEN_TIER_1) == TIER_BAND_DISPLAY_TIER_1
    assert tier_band_display_for(TIER_TOKEN_TIER_2) == TIER_BAND_DISPLAY_TIER_2
    assert tier_band_display_for(TIER_TOKEN_TIER_3) == TIER_BAND_DISPLAY_TIER_3


def test_tier_band_display_for_unknown_and_bad_input() -> None:
    assert tier_band_display_for(TIER_TOKEN_TIER_UNKNOWN) == DISPLAY_UNKNOWN
    assert tier_band_display_for(TIER_TOKEN_TIER_NOT_APPLICABLE) == (
        DISPLAY_UNKNOWN
    )
    assert tier_band_display_for("T2") == DISPLAY_UNKNOWN
    assert tier_band_display_for(None) == DISPLAY_UNKNOWN
    assert tier_band_display_for(2) == DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# 3. Input record shape + defaults
# ---------------------------------------------------------------------------


def test_required_fields_and_optional_defaults() -> None:
    record = PhoenixOperatorPingInput(
        token_mint="Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe",
        tier_token=TIER_TOKEN_TIER_2,
    )
    assert record.token_mint == (
        "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
    )
    assert record.tier_token == "Tier 2"
    # Every optional field defaults to None (renders as Unknown).
    for optional in (
        record.symbol_or_name,
        record.migration_confirmed,
        record.migration_time_utc,
        record.market_cap_display,
        record.liquidity_display,
        record.current_price,
        record.ath_price,
        record.absolute_drawdown,
        record.fractional_drop_pct,
        record.tier_band_display,
        record.basis_display,
        record.source_ref,
        record.age_display,
        record.ath_market_cap_display,
    ):
        assert optional is None


def test_record_is_immutable() -> None:
    record = PhoenixOperatorPingInput(token_mint="m" * 40, tier_token="Tier 1")
    # NamedTuple is immutable -- attribute assignment raises.
    try:
        record.token_mint = "other"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("PhoenixOperatorPingInput must be immutable")


# ---------------------------------------------------------------------------
# 4. Forbidden-field-name guard
# ---------------------------------------------------------------------------


def test_forbidden_record_field_names_flagged() -> None:
    for name in (
        "webhook",
        "webhook_url",
        "api_key",
        "bearer_token",
        "authorization",
        "secret",
        "private_key",
        "seed_phrase",
        "mnemonic",
        "raw_payload",
        "rpc_url",
    ):
        assert is_forbidden_record_field_name(name), name


def test_actual_record_field_names_are_not_forbidden() -> None:
    for name in PhoenixOperatorPingInput._fields:
        assert not is_forbidden_record_field_name(name), name


def test_forbidden_field_guard_total_on_non_string() -> None:
    assert is_forbidden_record_field_name(None) is False
    assert is_forbidden_record_field_name(123) is False
    assert isinstance(FORBIDDEN_RECORD_FIELD_NAMES, tuple)


# ---------------------------------------------------------------------------
# 5. Closed-set error
# ---------------------------------------------------------------------------


def test_error_carries_reason_token() -> None:
    err = Stage30_12PhoenixOperatorPingError("TOKEN_MINT_IS_WSOL_QUOTE")
    assert err.reason == "TOKEN_MINT_IS_WSOL_QUOTE"
    assert "TOKEN_MINT_IS_WSOL_QUOTE" in str(err)
