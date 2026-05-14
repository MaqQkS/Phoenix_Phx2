"""Stage 17 window constant + helper tests."""

from __future__ import annotations

import pytest

from PHX2.stage17.windows import (
    WINDOWS,
    ordered_window_seconds,
    window_label_for,
)


def test_windows_tuple_matches_locked_spec() -> None:
    assert WINDOWS == (
        (300, "5m"),
        (900, "15m"),
        (1800, "30m"),
        (3600, "1h"),
        (14400, "4h"),
        (86400, "24h"),
    )


def test_window_label_for_24h() -> None:
    assert window_label_for(86400) == "24h"


def test_window_label_for_5m() -> None:
    assert window_label_for(300) == "5m"


def test_window_label_for_15m() -> None:
    assert window_label_for(900) == "15m"


def test_window_label_for_30m() -> None:
    assert window_label_for(1800) == "30m"


def test_window_label_for_1h() -> None:
    assert window_label_for(3600) == "1h"


def test_window_label_for_4h() -> None:
    assert window_label_for(14400) == "4h"


def test_window_label_for_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError):
        window_label_for(99999)


def test_ordered_window_seconds_is_ascending() -> None:
    seconds = ordered_window_seconds()
    assert seconds == (300, 900, 1800, 3600, 14400, 86400)
    assert list(seconds) == sorted(seconds)
