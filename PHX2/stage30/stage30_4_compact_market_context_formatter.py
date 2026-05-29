"""Stage 30.4.1 offline compact market context formatter.

Pure formatting helpers for the Stage 30.4.1 adapter. The helpers
turn canonical decimal-text USD values into the preformatted
compact-display strings the Stage 30.2 compact ping renderer
consumes (``$83k`` / ``$1.2M`` / ``$27`` / ``$0`` and
``+$12k buys`` / ``-$8k sells`` / ``$0 flat``).

Discipline:

  * Stdlib only (``decimal`` / ``re`` / ``typing``).
  * Strict decimal-text input: callers MUST pass a ``str`` that the
    helper validates against a tight character pattern. ``float``,
    ``int``, ``Decimal``, ``None``, byte strings, and arbitrary
    objects are rejected.
  * Reject ``NaN`` / ``Infinity`` / signed-zero / leading-plus /
    leading-whitespace / trailing-whitespace / scientific-notation
    forms.
  * Reject negative MC / LP for the unsigned formatter.
  * No locale / no thread state / no implicit rounding mode flip.
  * No process-env read, no live secret access.
  * No network surface, no transport reference on source text.
  * No Stage 21-29 import.
  * No PHX1 import.
"""

from __future__ import annotations

import re
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_DOWN,
)


# ---------------------------------------------------------------------------
# Decimal-text gate
# ---------------------------------------------------------------------------
#
# A decimal-text string is one of:
#
#   * one or more ASCII digits (``0-9``),
#   * optionally with a leading ``-`` sign (signed formatter only),
#   * optionally followed by a single ``.`` and at least one ASCII
#     digit.
#
# Leading ``+``, leading or trailing whitespace, multiple signs,
# multiple dots, ``E`` / ``e`` notation, hex / octal / binary
# prefixes, underscores, ``NaN``, and ``Infinity`` literals are
# rejected.


_UNSIGNED_DECIMAL_PATTERN: re.Pattern[str] = re.compile(
    r"\A(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z"
)
_SIGNED_DECIMAL_PATTERN: re.Pattern[str] = re.compile(
    r"\A-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z"
)


_ONE_THOUSAND: Decimal = Decimal("1000")
_ONE_MILLION: Decimal = Decimal("1000000")


# ---------------------------------------------------------------------------
# Internal: parse strict decimal-text
# ---------------------------------------------------------------------------


def _parse_unsigned_decimal(value: object) -> Decimal:
    """Parse ``value`` as a strict unsigned decimal-text string.

    Raises ``ValueError`` on every non-canonical input, including
    ``float`` / ``int`` / ``Decimal`` / byte / ``None`` /
    arbitrary-object inputs, leading-plus, leading-minus, leading or
    trailing whitespace, multiple dots, scientific notation,
    ``NaN`` / ``Infinity`` literals, hex / octal / binary prefixes,
    and underscores.
    """
    if not isinstance(value, str):
        raise ValueError("USD_VALUE_NOT_DECIMAL_TEXT")
    if _UNSIGNED_DECIMAL_PATTERN.fullmatch(value) is None:
        raise ValueError("USD_VALUE_NOT_DECIMAL_TEXT")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ArithmeticError, TypeError) as _err:
        raise ValueError("USD_VALUE_NOT_DECIMAL_TEXT") from None
    if not parsed.is_finite():
        raise ValueError("USD_VALUE_NOT_FINITE")
    if parsed < 0:
        raise ValueError("USD_VALUE_NEGATIVE")
    return parsed


def _parse_signed_decimal(value: object) -> Decimal:
    """Parse ``value`` as a strict signed decimal-text string.

    Raises ``ValueError`` on every non-canonical input. Accepts a
    leading ``-`` for negative values; does NOT accept a leading
    ``+``.
    """
    if not isinstance(value, str):
        raise ValueError("USD_VALUE_NOT_DECIMAL_TEXT")
    if _SIGNED_DECIMAL_PATTERN.fullmatch(value) is None:
        raise ValueError("USD_VALUE_NOT_DECIMAL_TEXT")
    # Reject a literal ``"-0"`` form. ``Decimal("-0")`` is finite
    # but the renderer's "$0 flat" / "$0" outputs must come from a
    # caller that wrote a positive zero.
    if value == "-0":
        raise ValueError("USD_VALUE_NOT_DECIMAL_TEXT")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ArithmeticError, TypeError) as _err:
        raise ValueError("USD_VALUE_NOT_DECIMAL_TEXT") from None
    if not parsed.is_finite():
        raise ValueError("USD_VALUE_NOT_FINITE")
    return parsed


# ---------------------------------------------------------------------------
# Internal: render magnitude
# ---------------------------------------------------------------------------


def _render_magnitude(magnitude: Decimal) -> str:
    """Render a non-negative finite ``Decimal`` magnitude as the
    compact USD body string WITHOUT a leading sign and WITHOUT a
    leading ``$`` glyph.

    Mapping:

      * ``magnitude == 0``           -> ``"0"``
      * ``magnitude < 1000``         -> ``"<int>"`` (truncated to
                                        the integer with
                                        ``ROUND_DOWN``).
      * ``1000 <= magnitude``        -> ``"<x>k"`` / ``"<x.y>k"``
        ``< 1_000_000``                with one decimal place when
                                        the truncated tenths digit
                                        is non-zero
                                        (``ROUND_DOWN``).
      * ``magnitude >= 1_000_000``   -> ``"<x>M"`` / ``"<x.y>M"``
                                        with one decimal place when
                                        the truncated tenths digit
                                        is non-zero
                                        (``ROUND_DOWN``).

    Truncation (``ROUND_DOWN``) is used so a partial value is never
    rounded up into the next bucket (e.g. ``"999999"`` renders as
    ``"999.9k"``, not ``"1M"``; ``"1234567"`` renders as ``"1.2M"``,
    not ``"1.3M"``). This keeps the rendered compact body
    pessimistic about magnitude (Stage 30 never overstates MC / LP /
    Net flow).
    """
    if magnitude == 0:
        return "0"
    if magnitude < _ONE_THOUSAND:
        truncated_int = magnitude.to_integral_value(
            rounding=ROUND_DOWN
        )
        return f"{int(truncated_int)}"
    if magnitude < _ONE_MILLION:
        thousands = magnitude / _ONE_THOUSAND
        truncated_tenth = thousands.quantize(
            Decimal("0.1"), rounding=ROUND_DOWN
        )
        if truncated_tenth == truncated_tenth.to_integral_value():
            int_part = int(
                truncated_tenth.to_integral_value(
                    rounding=ROUND_DOWN
                )
            )
            return f"{int_part}k"
        return f"{truncated_tenth}k"
    millions = magnitude / _ONE_MILLION
    truncated_tenth = millions.quantize(
        Decimal("0.1"), rounding=ROUND_DOWN
    )
    if truncated_tenth == truncated_tenth.to_integral_value():
        int_part = int(
            truncated_tenth.to_integral_value(
                rounding=ROUND_DOWN
            )
        )
        return f"{int_part}M"
    return f"{truncated_tenth}M"


# ---------------------------------------------------------------------------
# Public: format_usd_compact (unsigned)
# ---------------------------------------------------------------------------


def format_usd_compact(value: str) -> str:
    """Return the compact display string for a non-negative
    decimal-text USD value.

      * ``"83000"``      -> ``"$83k"``
      * ``"1200000"``    -> ``"$1.2M"``
      * ``"27"``         -> ``"$27"``
      * ``"0"``          -> ``"$0"`` (use ONLY when the caller's
                            source explicitly reports a known zero;
                            for missing source / missing value the
                            caller should NEVER call this helper
                            and should record Unknown instead).

    Raises ``ValueError`` with a closed-set reason token on:

      * non-``str`` input,
      * non-decimal-text (NaN, Infinity, scientific notation,
        leading plus, whitespace, multiple dots, hex / octal /
        binary prefix, underscore digit grouping),
      * negative values.
    """
    magnitude = _parse_unsigned_decimal(value)
    body = _render_magnitude(magnitude)
    return f"${body}"


# ---------------------------------------------------------------------------
# Public: format_signed_usd_compact (signed)
# ---------------------------------------------------------------------------


def format_signed_usd_compact(
    value: str,
    positive_label: str = "buys",
    negative_label: str = "sells",
) -> str:
    """Return the compact display string for a signed decimal-text
    USD net flow value.

      * ``"12000"``      -> ``"+$12k buys"``
      * ``"-8000"``      -> ``"-$8k sells"``
      * ``"0"``          -> ``"$0 flat"``

    ``positive_label`` and ``negative_label`` are short ASCII
    alphanumeric labels (``[A-Za-z0-9_-]+`` shape; length [1, 16]).
    Default labels are ``"buys"`` / ``"sells"``.

    Raises ``ValueError`` with a closed-set reason token on:

      * non-``str`` value input,
      * non-decimal-text value,
      * NaN / Infinity / leading-plus / whitespace / scientific
        notation,
      * label of the wrong shape.
    """
    _validate_label(positive_label)
    _validate_label(negative_label)
    parsed = _parse_signed_decimal(value)
    if parsed == 0:
        return "$0 flat"
    if parsed > 0:
        body = _render_magnitude(parsed)
        return f"+${body} {positive_label}"
    magnitude = -parsed
    body = _render_magnitude(magnitude)
    return f"-${body} {negative_label}"


# ---------------------------------------------------------------------------
# Internal: label shape gate
# ---------------------------------------------------------------------------


_LABEL_PATTERN: re.Pattern[str] = re.compile(
    r"\A[A-Za-z0-9_\-]{1,16}\Z"
)


def _validate_label(label: object) -> None:
    """Raise ``ValueError`` iff ``label`` is not a safe-shape short
    ASCII alphanumeric label.
    """
    if not isinstance(label, str):
        raise ValueError("LABEL_NOT_STRING")
    if _LABEL_PATTERN.fullmatch(label) is None:
        raise ValueError("LABEL_SHAPE_INVALID")


__all__ = (
    "format_usd_compact",
    "format_signed_usd_compact",
)
