"""Pure formatting helpers for the PHX2 renderer.

Each formatter accepts ``None`` and returns the canonical missing placeholder
``"unknown"``. Formatters never raise; bad numeric inputs (NaN, inf, non-numeric
strings) collapse to ``"unknown"`` so the renderer can stay total over its
inputs.

These functions are pure: no clock reads, no environment access, no I/O. They
are imported by both :mod:`PHX2.renderers.alert_renderer` (the renderer) and
:mod:`PHX2.renderers.adapters.plain_text` (an adapter).
"""

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Optional


UNKNOWN = "unknown"


def _coerce_float(value: Any) -> Optional[float]:
    """Return a finite float or ``None``. Used internally by numeric formatters."""

    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(result):
        return None
    return result


def format_mcap(value: Any) -> str:
    """Format a market cap or USD price value with K/M scaling."""

    amount = _coerce_float(value)
    if amount is None:
        return UNKNOWN
    abs_amount = abs(amount)
    sign = "-" if amount < 0 else ""
    if abs_amount >= 1_000_000:
        return f"{sign}${abs_amount / 1_000_000:.2f}M"
    if abs_amount >= 1_000:
        scaled = abs_amount / 1_000
        if scaled >= 100:
            return f"{sign}${scaled:.0f}K"
        return f"{sign}${scaled:.2f}K"
    if abs_amount >= 1:
        return f"{sign}${abs_amount:.2f}"
    if abs_amount == 0:
        return "$0.00"
    if abs_amount < 0.001:
        return f"{sign}${abs_amount:.6e}"
    return f"{sign}${abs_amount:.6f}".rstrip("0").rstrip(".")


def format_pump_multiple(value: Any) -> str:
    """Format a pump multiple as ``X.XXx``."""

    multiple = _coerce_float(value)
    if multiple is None:
        return UNKNOWN
    return f"{multiple:.2f}x"


def format_percent(value: Any) -> str:
    """Format a fraction (0..1) as ``XX.X%``. Accepts negative values too."""

    fraction = _coerce_float(value)
    if fraction is None:
        return UNKNOWN
    return f"{fraction * 100:.1f}%"


def format_duration(seconds: Any) -> str:
    """Format a duration in seconds with adaptive units."""

    raw = _coerce_float(seconds)
    if raw is None:
        return UNKNOWN
    total_seconds = int(raw)
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    if total_seconds < 60:
        return f"{sign}{total_seconds}s"
    if total_seconds < 3600:
        minutes, secs = divmod(total_seconds, 60)
        return f"{sign}{minutes}m {secs}s"
    if total_seconds < 86400:
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        return f"{sign}{hours}h {minutes}m"
    days, remainder = divmod(total_seconds, 86400)
    hours = remainder // 3600
    return f"{sign}{days}d {hours}h"


def format_timestamp(value: Any) -> str:
    """Format a datetime as ISO 8601 in UTC with explicit ``Z`` suffix."""

    if not isinstance(value, datetime):
        return UNKNOWN
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_address_short(address: Any) -> str:
    """Truncate an address as ``first4...last4``. Short inputs render unchanged."""

    if address is None:
        return UNKNOWN
    if not isinstance(address, str):
        return UNKNOWN
    if len(address) <= 10:
        return address
    return f"{address[:4]}...{address[-4:]}"


def format_address_full(address: Any) -> str:
    """Return the address verbatim, or ``"unknown"`` if missing."""

    if address is None:
        return UNKNOWN
    if not isinstance(address, str):
        return UNKNOWN
    return address


def format_price_age(seconds: Any) -> str:
    """Format a price age in seconds as ``Xs`` for sub-minute, else use duration."""

    raw = _coerce_float(seconds)
    if raw is None:
        return UNKNOWN
    if raw < 0:
        return format_duration(seconds)
    if raw < 60:
        return f"{int(raw)}s"
    return format_duration(seconds)


def format_string(value: Any) -> str:
    """Render an arbitrary scalar as its string form, ``None`` becomes ``"unknown"``."""

    if value is None:
        return UNKNOWN
    if isinstance(value, str):
        if not value:
            return UNKNOWN
        return value
    return str(value)
