"""Tests for Stage 20 clock helper (20.1.D)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from PHX2.stage20.clock import (
    FrozenClock,
    SystemClock,
    default_clock,
)


def test_system_clock_returns_tz_aware_utc_datetime():
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() is not None
    assert now.utcoffset().total_seconds() == 0


def test_frozen_clock_returns_fixed_value_idempotently():
    fixed = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    fc = FrozenClock(fixed)
    first = fc.now()
    second = fc.now()
    assert first == fixed
    assert second == fixed
    assert first == second


def test_frozen_clock_rejects_naive_datetime():
    naive = datetime(2026, 5, 14, 12, 0, 0)
    with pytest.raises(ValueError):
        FrozenClock(naive)


def test_default_clock_is_system_clock():
    assert isinstance(default_clock(), SystemClock)
