"""Stage 21 injectable clock helper.

Stage 21 follows the Stage 20 clock-pattern verbatim: every
runtime function that needs the current wall time accepts a
``clock`` keyword argument and calls ``clock.now()``; tests inject
a ``FrozenClock`` for byte-deterministic output.

The Stage 21 boundary tests assert NO Stage 21 module outside this
file calls ``datetime.utcnow()`` or ``datetime.now(timezone.utc)``.

Stage 21 deliberately uses its own Clock type (rather than
re-exporting Stage 20's) because the Stage 21 import-boundary
policy forbids ``import PHX2.stage20`` at runtime. The
implementation here is identical in shape; duplication is the
contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    """Anything that exposes ``now() -> tz-aware UTC datetime``."""

    def now(self) -> datetime: ...


class SystemClock:
    """Real-clock implementation backed by ``datetime.now(timezone.utc)``.

    The only ``datetime.now(timezone.utc)`` call anywhere in Stage 21
    production code lives here. Every other Stage 21 module reads
    wall time via an injected ``Clock`` instance, never via the
    stdlib ``datetime`` module directly.
    """

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock:
    """Deterministic clock for tests.

    Always returns the fixed tz-aware UTC datetime supplied at
    construction. A naive datetime is rejected with ``ValueError``
    so Stage 21 production code that reads ``clock.now()`` can
    safely assume tz-aware UTC.

    Tests that need to advance the clock construct a new
    ``FrozenClock`` rather than mutating an existing one. The
    instance itself is intentionally immutable in its observable
    behavior.
    """

    def __init__(self, fixed: datetime) -> None:
        if fixed.tzinfo is None:
            raise ValueError(
                "FrozenClock requires a tz-aware datetime; got a naive one"
            )
        if fixed.utcoffset() != timezone.utc.utcoffset(fixed):
            raise ValueError(
                "FrozenClock requires UTC tz-info; got a non-UTC offset"
            )
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed


def default_clock() -> Clock:
    """Return the production clock instance (``SystemClock``).

    Stage 21 runtime functions that take ``clock`` default to this
    via ``clock = clock or default_clock()``. Tests pass an explicit
    ``FrozenClock`` and never hit ``default_clock()``.
    """

    return SystemClock()


__all__ = ["Clock", "FrozenClock", "SystemClock", "default_clock"]
