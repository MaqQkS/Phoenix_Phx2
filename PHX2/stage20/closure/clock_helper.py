"""Stage 20.4 injectable clock helper (closure-local copy).

Boundary discipline: this module is a hand-duplicated, local
copy of the Stage 20 injectable-clock idiom. Stage 20.4 closure
production code does NOT import from ``PHX2.stage20.clock``; the
duplication preserves the locked import-boundary policy for the
closure subtree (mirrors the 20.1 hand-duplication precedent
that kept Stage 18/19 schema constants out of cross-stage
imports).

Public surface:

  * ``Clock`` (Protocol)        -- anything with ``now()`` returning a
                                   tz-aware UTC datetime.
  * ``SystemClock``             -- real-clock implementation.
  * ``FrozenClock(fixed)``      -- deterministic clock for tests;
                                   rejects naive datetimes.
  * ``default_clock()``         -- returns ``SystemClock()``.
  * ``format_utc_iso_z(dt)``    -- ISO-8601 ``"Z"``-suffixed
                                   formatter; matches Stage 20.2's
                                   ``runner._format_iso_z`` and
                                   Stage 20.3's
                                   ``filter_interface_runner._format_iso_z``
                                   so the ``generated_at_utc``
                                   string format is identical
                                   across 20.2 / 20.3 / 20.4.

Phoenix1 departure note: this module imports no Phoenix1 code.

Known limitations (v0):

  * ``FrozenClock`` rejects naive datetimes with ``ValueError``;
    callers must always inject a tz-aware UTC value.
  * No ambient-clock fallback. Callers either supply a clock or
    call ``default_clock()`` to obtain the production
    ``SystemClock`` instance.

What Stage 20.4 will NOT do (relevant here):

  * No wall-clock reads outside ``SystemClock.now``; every other
    closure module derives timestamps via an injected clock.
  * No monkeypatching of stdlib ``datetime``; ``FrozenClock`` is
    the deterministic test seam.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


_ISO_Z_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"


class Clock(Protocol):
    """Anything that exposes ``now()`` returning a tz-aware UTC datetime."""

    def now(self) -> datetime: ...


class SystemClock:
    """Real-clock implementation: returns tz-aware UTC system time."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock:
    """Deterministic clock for tests.

    Always returns the fixed tz-aware UTC datetime supplied at
    construction. Raises ``ValueError`` if a naive datetime is
    passed -- closure code assumes tz-aware UTC throughout.
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
    """Return the production clock instance (``SystemClock``)."""

    return SystemClock()


def format_utc_iso_z(dt: datetime) -> str:
    """Format a tz-aware UTC datetime to ``YYYY-MM-DDTHH:MM:SSZ``.

    Pinned to the same convention used by Stage 20.2 / 20.3 so
    every Stage 20 stage emits an identical ``generated_at_utc``
    string for the same input.

    Raises:
        ValueError: if ``dt`` is naive (no tzinfo).
    """

    if dt.tzinfo is None:
        raise ValueError(
            "format_utc_iso_z requires a tz-aware datetime; got a naive one"
        )
    return dt.strftime(_ISO_Z_FORMAT)


__all__ = [
    "Clock",
    "FrozenClock",
    "SystemClock",
    "default_clock",
    "format_utc_iso_z",
]
