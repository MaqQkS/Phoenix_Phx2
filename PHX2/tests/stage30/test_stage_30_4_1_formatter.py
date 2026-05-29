"""Stage 30.4.1 compact market context formatter tests.

Pure offline tests over the format_usd_compact and
format_signed_usd_compact helpers. No live network, no env, no
Discord.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_4_compact_market_context_formatter import (
    format_signed_usd_compact,
    format_usd_compact,
)


# ---------------------------------------------------------------------------
# format_usd_compact: golden cases from the spec
# ---------------------------------------------------------------------------


def test_format_usd_compact_golden_83000() -> None:
    assert format_usd_compact("83000") == "$83k"


def test_format_usd_compact_golden_1200000() -> None:
    assert format_usd_compact("1200000") == "$1.2M"


def test_format_usd_compact_golden_27() -> None:
    assert format_usd_compact("27") == "$27"


def test_format_usd_compact_golden_known_zero() -> None:
    """Stage 30.4.1 spec: ``"0"`` -> ``"$0"`` ONLY when the caller
    explicitly supplies a known zero. The formatter does NOT decide
    when zero is "real"; the caller (adapter) decides whether to
    forward Unknown OR call the formatter.
    """
    assert format_usd_compact("0") == "$0"


# ---------------------------------------------------------------------------
# format_usd_compact: bucket boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("1", "$1"),
        ("999", "$999"),
        ("1000", "$1k"),
        ("1500", "$1.5k"),
        ("12345", "$12.3k"),
        ("999999", "$999.9k"),
        ("1000000", "$1M"),
        ("1234567", "$1.2M"),
        ("9999999", "$9.9M"),
        ("100000000", "$100M"),
    ],
)
def test_format_usd_compact_bucket_boundaries(
    input_text: str, expected: str
) -> None:
    assert format_usd_compact(input_text) == expected


# ---------------------------------------------------------------------------
# format_usd_compact: rounds DOWN (never up)
# ---------------------------------------------------------------------------


def test_format_usd_compact_truncates_no_rounding_up() -> None:
    # 12999 -> $12.9k, NOT $13k.
    assert format_usd_compact("12999") == "$12.9k"
    # 1999999 -> $1.9M, NOT $2M.
    assert format_usd_compact("1999999") == "$1.9M"


# ---------------------------------------------------------------------------
# format_usd_compact: rejects non-decimal-text input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [
        None,
        123,
        0,
        0.0,
        1.5,
        -1,
        -1.5,
        True,
        False,
        b"83000",
        bytearray(b"100"),
        [83000],
        {"v": 100},
        Decimal("83000"),
        Decimal("1.5"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_format_usd_compact_rejects_non_decimal_text(
    bad_value: object,
) -> None:
    with pytest.raises(ValueError):
        # mypy / pylance: intentionally pass off-type values to
        # exercise the type gate.
        format_usd_compact(bad_value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_text",
    [
        "",
        " 83000",
        "83000 ",
        " ",
        "+83000",
        "-83000",
        "-0",
        "8.3e4",
        "8.3E4",
        "83_000",
        "0x100",
        "0o100",
        "0b100",
        "NaN",
        "Infinity",
        "-Infinity",
        "Inf",
        "nan",
        "inf",
        "83000abc",
        "abc83000",
        "8,3000",
        "83000.",
        ".5",
        "0..5",
        "1.0.0",
        "1..5",
        "-",
        ".",
        "1,000",
    ],
)
def test_format_usd_compact_rejects_non_canonical_decimal_text(
    bad_text: str,
) -> None:
    with pytest.raises(ValueError):
        format_usd_compact(bad_text)


# ---------------------------------------------------------------------------
# format_usd_compact: enforces non-negative
# ---------------------------------------------------------------------------


def test_format_usd_compact_rejects_negative_via_decimal_text() -> None:
    # Unsigned formatter pattern does NOT allow a leading "-".
    with pytest.raises(ValueError):
        format_usd_compact("-1000")
    with pytest.raises(ValueError):
        format_usd_compact("-83000")


# ---------------------------------------------------------------------------
# format_signed_usd_compact: golden cases from the spec
# ---------------------------------------------------------------------------


def test_format_signed_usd_compact_golden_positive() -> None:
    assert format_signed_usd_compact("12000") == "+$12k buys"


def test_format_signed_usd_compact_golden_negative() -> None:
    assert format_signed_usd_compact("-8000") == "-$8k sells"


def test_format_signed_usd_compact_golden_zero() -> None:
    assert format_signed_usd_compact("0") == "$0 flat"


# ---------------------------------------------------------------------------
# format_signed_usd_compact: bucket boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("1", "+$1 buys"),
        ("999", "+$999 buys"),
        ("1000", "+$1k buys"),
        ("1500", "+$1.5k buys"),
        ("12000", "+$12k buys"),
        ("12345", "+$12.3k buys"),
        ("999999", "+$999.9k buys"),
        ("1000000", "+$1M buys"),
        ("1234567", "+$1.2M buys"),
        ("-1", "-$1 sells"),
        ("-999", "-$999 sells"),
        ("-1000", "-$1k sells"),
        ("-1500", "-$1.5k sells"),
        ("-8000", "-$8k sells"),
        ("-1000000", "-$1M sells"),
        ("0", "$0 flat"),
    ],
)
def test_format_signed_usd_compact_bucket_boundaries(
    input_text: str, expected: str
) -> None:
    assert format_signed_usd_compact(input_text) == expected


# ---------------------------------------------------------------------------
# format_signed_usd_compact: rejects non-decimal-text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [
        None,
        12000,
        0.0,
        -8000.0,
        True,
        b"12000",
        Decimal("12000"),
        Decimal("NaN"),
        Decimal("Infinity"),
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_format_signed_usd_compact_rejects_non_decimal_text(
    bad_value: object,
) -> None:
    with pytest.raises(ValueError):
        format_signed_usd_compact(bad_value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_text",
    [
        "",
        " 12000",
        "12000 ",
        "+12000",
        "-0",
        "1.2e4",
        "1.2E4",
        "12_000",
        "NaN",
        "Infinity",
        "-Infinity",
        "nan",
        "inf",
        "12000abc",
        "12,000",
        ".5",
        "12000.",
        "--12000",
        "-",
    ],
)
def test_format_signed_usd_compact_rejects_non_canonical_decimal_text(
    bad_text: str,
) -> None:
    with pytest.raises(ValueError):
        format_signed_usd_compact(bad_text)


# ---------------------------------------------------------------------------
# format_signed_usd_compact: label shape gate
# ---------------------------------------------------------------------------


def test_format_signed_usd_compact_custom_labels() -> None:
    assert (
        format_signed_usd_compact(
            "12000",
            positive_label="bull",
            negative_label="bear",
        )
        == "+$12k bull"
    )
    assert (
        format_signed_usd_compact(
            "-8000",
            positive_label="bull",
            negative_label="bear",
        )
        == "-$8k bear"
    )


@pytest.mark.parametrize(
    "bad_label",
    [
        "",
        " ",
        "buys ",
        " buys",
        "a" * 17,
        "label with space",
        "label!",
        "label.",
        "🚀",
        None,
        123,
    ],
)
def test_format_signed_usd_compact_rejects_bad_positive_label(
    bad_label: object,
) -> None:
    with pytest.raises(ValueError):
        format_signed_usd_compact(
            "12000",
            positive_label=bad_label,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "bad_label",
    [
        "",
        " ",
        "sells ",
        "a" * 17,
        None,
        123,
    ],
)
def test_format_signed_usd_compact_rejects_bad_negative_label(
    bad_label: object,
) -> None:
    with pytest.raises(ValueError):
        format_signed_usd_compact(
            "-8000",
            negative_label=bad_label,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Defensive: math.nan / math.inf rejection
# ---------------------------------------------------------------------------


def test_format_usd_compact_rejects_math_nan_math_inf() -> None:
    with pytest.raises(ValueError):
        format_usd_compact(math.nan)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        format_usd_compact(math.inf)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        format_usd_compact(-math.inf)  # type: ignore[arg-type]


def test_format_signed_usd_compact_rejects_math_nan_math_inf() -> None:
    with pytest.raises(ValueError):
        format_signed_usd_compact(math.nan)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        format_signed_usd_compact(math.inf)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        format_signed_usd_compact(-math.inf)  # type: ignore[arg-type]
