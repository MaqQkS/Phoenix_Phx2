"""Tests for PHX2 renderer formatters."""

from datetime import datetime, timedelta, timezone

from PHX2.renderers.formatters import (
    UNKNOWN,
    format_address_full,
    format_address_short,
    format_duration,
    format_mcap,
    format_percent,
    format_price_age,
    format_pump_multiple,
    format_string,
    format_timestamp,
)


# ---- format_mcap ---------------------------------------------------------


def test_format_mcap_handles_none():
    assert format_mcap(None) == UNKNOWN


def test_format_mcap_handles_invalid_inputs():
    assert format_mcap(float("nan")) == UNKNOWN
    assert format_mcap(float("inf")) == UNKNOWN
    assert format_mcap("not-a-number") == UNKNOWN


def test_format_mcap_millions_uses_two_decimals():
    assert format_mcap(2_840_000) == "$2.84M"
    assert format_mcap(1_020_000) == "$1.02M"


def test_format_mcap_thousands_under_one_hundred_K_uses_two_decimals():
    assert format_mcap(3_120) == "$3.12K"


def test_format_mcap_thousands_over_one_hundred_K_uses_zero_decimals():
    assert format_mcap(847_000) == "$847K"


def test_format_mcap_under_one_thousand():
    assert format_mcap(42.18) == "$42.18"


def test_format_mcap_zero():
    assert format_mcap(0) == "$0.00"


def test_format_mcap_tiny_uses_scientific():
    rendered = format_mcap(0.000042)
    assert rendered.startswith("$") and "e" in rendered.lower()


# ---- format_pump_multiple ------------------------------------------------


def test_format_pump_multiple_handles_none():
    assert format_pump_multiple(None) == UNKNOWN


def test_format_pump_multiple_two_decimals():
    assert format_pump_multiple(1.42) == "1.42x"
    assert format_pump_multiple(2.71) == "2.71x"
    assert format_pump_multiple(12.4) == "12.40x"


def test_format_pump_multiple_handles_invalid():
    assert format_pump_multiple(float("nan")) == UNKNOWN


# ---- format_percent ------------------------------------------------------


def test_format_percent_handles_none():
    assert format_percent(None) == UNKNOWN


def test_format_percent_one_decimal():
    assert format_percent(0.623) == "62.3%"
    assert format_percent(0.08) == "8.0%"
    assert format_percent(0.702) == "70.2%"


def test_format_percent_handles_invalid():
    assert format_percent(float("inf")) == UNKNOWN


# ---- format_duration ----------------------------------------------------


def test_format_duration_handles_none():
    assert format_duration(None) == UNKNOWN


def test_format_duration_zero():
    assert format_duration(0) == "0s"


def test_format_duration_sub_minute():
    assert format_duration(42) == "42s"


def test_format_duration_minute_boundary():
    assert format_duration(60) == "1m 0s"


def test_format_duration_minutes():
    assert format_duration(252) == "4m 12s"


def test_format_duration_hour_boundary():
    assert format_duration(3600) == "1h 0m"


def test_format_duration_hours():
    assert format_duration(8280) == "2h 18m"


def test_format_duration_day_boundary():
    assert format_duration(86400) == "1d 0h"


def test_format_duration_days():
    assert format_duration(97200) == "1d 3h"


def test_format_duration_handles_sub_second():
    # Sub-second floats truncate to zero seconds, which still renders cleanly.
    assert format_duration(0.4) == "0s"


def test_format_duration_handles_invalid():
    assert format_duration("not-numeric") == UNKNOWN


# ---- format_timestamp ---------------------------------------------------


def test_format_timestamp_handles_none():
    assert format_timestamp(None) == UNKNOWN


def test_format_timestamp_naive_treated_as_utc():
    naive = datetime(2026, 5, 9, 14, 33, 4)
    assert format_timestamp(naive) == "2026-05-09T14:33:04Z"


def test_format_timestamp_aware_utc_renders_z():
    aware = datetime(2026, 5, 9, 14, 33, 4, tzinfo=timezone.utc)
    assert format_timestamp(aware) == "2026-05-09T14:33:04Z"


def test_format_timestamp_aware_non_utc_normalizes_to_utc():
    eastern = timezone(timedelta(hours=-5))
    value = datetime(2026, 5, 9, 9, 33, 4, tzinfo=eastern)
    assert format_timestamp(value) == "2026-05-09T14:33:04Z"


def test_format_timestamp_handles_non_datetime():
    assert format_timestamp("not-a-datetime") == UNKNOWN


# ---- format_address_short -----------------------------------------------


def test_format_address_short_handles_none():
    assert format_address_short(None) == UNKNOWN


def test_format_address_short_truncates_long_address():
    address = "7xKp9aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890mLq"
    assert format_address_short(address) == "7xKp...0mLq"


def test_format_address_short_returns_short_address_unchanged():
    assert format_address_short("abc") == "abc"
    assert format_address_short("0123456789") == "0123456789"


def test_format_address_short_rejects_non_string():
    assert format_address_short(12345) == UNKNOWN


# ---- format_address_full ------------------------------------------------


def test_format_address_full_handles_none():
    assert format_address_full(None) == UNKNOWN


def test_format_address_full_passes_through():
    address = "7xKp9aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890mLq"
    assert format_address_full(address) == address


def test_format_address_full_rejects_non_string():
    assert format_address_full(123) == UNKNOWN


# ---- format_price_age ---------------------------------------------------


def test_format_price_age_handles_none():
    assert format_price_age(None) == UNKNOWN


def test_format_price_age_under_minute_uses_seconds():
    assert format_price_age(42) == "42s"
    assert format_price_age(142) == "2m 22s"


def test_format_price_age_invalid_returns_unknown():
    assert format_price_age(float("nan")) == UNKNOWN


# ---- format_string -------------------------------------------------------


def test_format_string_handles_none_and_empty():
    assert format_string(None) == UNKNOWN
    assert format_string("") == UNKNOWN


def test_format_string_passes_through():
    assert format_string("hello") == "hello"


def test_format_string_coerces_non_string():
    assert format_string(42) == "42"
