"""Stage 17 window-seconds -> short-label mapping.

This is a deliberate local copy of Stage 12's mapping. Stage 17 must
not import from ``PHX2.analysis`` (boundary lock) so the same constant
is restated here. The locked outcome_windows CHECK constraint pins
the underlying set: ``window_seconds IN (300, 900, 1800, 3600, 14400,
86400)``.
"""

from __future__ import annotations

from typing import Tuple


WINDOWS: Tuple[Tuple[int, str], ...] = (
    (300, "5m"),
    (900, "15m"),
    (1800, "30m"),
    (3600, "1h"),
    (14400, "4h"),
    (86400, "24h"),
)


_WINDOW_LABEL_BY_SECONDS: dict[int, str] = {seconds: label for seconds, label in WINDOWS}


def window_label_for(window_seconds: int) -> str:
    """Return the short label for a known window-seconds value.

    Raises ``KeyError`` on an unknown value. Stage 17 only calls this
    for values that came from the locked outcome_windows CHECK set; an
    unknown value means the source schema changed and the caller
    should surface the failure rather than silently render "?".
    """

    return _WINDOW_LABEL_BY_SECONDS[window_seconds]


def ordered_window_seconds() -> Tuple[int, ...]:
    """Return the locked window-seconds tuple in ascending order."""

    return tuple(seconds for seconds, _ in WINDOWS)
