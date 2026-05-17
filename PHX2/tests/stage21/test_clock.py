"""Stage 21 clock tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from PHX2.stage21.clock import (
    Clock,
    FrozenClock,
    SystemClock,
    default_clock,
)


def test_frozen_clock_returns_fixed_value():
    fixed = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    clock = FrozenClock(fixed)
    assert clock.now() == fixed
    # Independent of repeated calls.
    assert clock.now() == fixed


def test_frozen_clock_rejects_naive_datetime():
    naive = datetime(2026, 5, 17, 12, 0, 0)
    with pytest.raises(ValueError):
        FrozenClock(naive)


def test_frozen_clock_rejects_non_utc_offset():
    other = timezone(timedelta(hours=3))
    with pytest.raises(ValueError):
        FrozenClock(datetime(2026, 5, 17, 12, 0, 0, tzinfo=other))


def test_system_clock_returns_tz_aware_utc():
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_default_clock_returns_system_clock_instance():
    clock = default_clock()
    assert isinstance(clock, SystemClock)


def test_clock_protocol_accepts_fake_implementation():
    class FakeClock:
        def now(self) -> datetime:
            return datetime(2026, 1, 1, tzinfo=timezone.utc)

    fake: Clock = FakeClock()
    # Protocol membership is structural; the assignment above
    # would have failed at type-check time if the shape was wrong.
    # Behavior verification keeps the test runtime-meaningful.
    assert fake.now() == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_frozen_clock_is_deterministic_across_calls_and_independent_instances():
    fixed = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    a = FrozenClock(fixed)
    b = FrozenClock(fixed)
    assert a.now() == b.now()
