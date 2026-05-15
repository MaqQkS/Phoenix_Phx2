"""Stage 20 injectable clock helper.

Stage 20 validators accept ``clock`` as a keyword argument and
call ``clock.now()`` for the current UTC datetime. Tests inject a
``FrozenClock`` with a fixed value so validation is deterministic.

Production code uses ``SystemClock`` (selected via
``default_clock()`` when no explicit clock is supplied). Wall-clock
time is read only from this module's ``SystemClock.now``; no
validator imports ``datetime.utcnow()`` or
``datetime.now(timezone.utc)`` directly.

Rationale (STEP 0 finding): the prior PHX2 stages (16A/16B/17/
18/19) do not ship a shared clock-wrapper module; their CLIs
take an explicit ``--run-timestamp`` scalar for determinism and
fall back to ``datetime.now(timezone.utc)`` at the CLI boundary.
Stage 20 introduces this clock helper so validator-level
determinism does not depend on a CLI scalar; tests pass an
explicit ``FrozenClock`` into ``validate_inputs(... , clock=...)``
without monkeypatching the stdlib ``datetime`` module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    """Anything that exposes ``now() -> tz-aware UTC datetime``."""

    def now(self) -> datetime: ...


class SystemClock:
    """Real-clock implementation backed by ``datetime.now(timezone.utc)``."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock:
    """Deterministic clock for tests.

    Always returns the fixed tz-aware UTC datetime supplied at
    construction. ``ValueError`` is raised if a naive datetime is
    passed -- the validator code assumes tz-aware UTC inputs.
    """

    def __init__(self, fixed: datetime) -> None:
        if fixed.tzinfo is None:
            raise ValueError(
                "FrozenClock requires a tz-aware datetime; got a naive one"
            )
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed


def default_clock() -> Clock:
    """Return the production clock instance (``SystemClock``).

    Used by ``validate_inputs`` when no ``clock`` argument is
    supplied.
    """

    return SystemClock()


__all__ = ["Clock", "FrozenClock", "SystemClock", "default_clock"]
