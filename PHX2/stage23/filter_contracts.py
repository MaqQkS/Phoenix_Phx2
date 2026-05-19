"""Stage 23 observe-only filter contract surface (foundation only at 23.1).

This module ships the typed ``Protocol`` surface every Stage
23.2+ filter must satisfy, plus the ``Stage23FilterFamily``
closed-set helper that callers use to look up the family token
for a filter without re-implementing the closed-set lookup.

Surfaces:

  * ``Stage23FilterFamily``  -- closed-set helper. Wraps the
                                ``FILTER_FAMILIES`` tuple in a
                                namespaced class so callers can
                                use ``Stage23FilterFamily.MEMBERS``
                                / ``.contains`` without re-deriving
                                the membership predicate.
  * ``Stage23Filter``        -- the ``Protocol`` every Stage 23.2+
                                filter satisfies. One method:
                                ``evaluate(filter_input)`` returns
                                a ``Stage23FilterResult``.

Design notes:

  * The Protocol is for FAKES and downstream callers. Stage 23.1
    ships NO filter implementation; the Protocol locks the
    surface so 23.2 / 23.3 / 23.4 can land additively without
    shape churn.
  * Filters are pure functions over a ``Stage23FilterInput`` --
    no side effects, no network calls, no env reads. The
    Protocol does not pin those invariants at the type system
    level, but the Stage 23 boundary tests assert them at the
    AST / import level.
  * Filter implementations are responsible for setting
    ``filter_name`` / ``filter_family`` / ``filter_version`` /
    ``threshold_version`` on every produced result. The
    Stage 23 boundary tests will pin the exact ``filter_name``
    vocabulary in the 23.2+ closure tests; 23.1 does not lock
    individual filter names.

This module imports only stdlib (``typing``) plus the Stage 23
constants and models. It does NOT import Stage 21 or Stage 22
modules, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and
contains no top-level I/O.
"""

from __future__ import annotations

from typing import Protocol

from PHX2.stage23.constants import FILTER_FAMILIES
from PHX2.stage23.models import Stage23FilterInput, Stage23FilterResult


# ---------------------------------------------------------------------------
# Stage23FilterFamily -- closed-set helper
# ---------------------------------------------------------------------------


class Stage23FilterFamily:
    """Closed-set helper for the Stage 23 filter-family tokens.

    Wraps the ``FILTER_FAMILIES`` tuple so callers can use a
    namespaced class without re-implementing membership lookup.
    Adding a member requires a contract patch to
    ``PHX2/stage23/constants.py``.
    """

    MEMBERS: tuple[str, ...] = FILTER_FAMILIES

    @classmethod
    def contains(cls, value: str) -> bool:
        return value in cls.MEMBERS


# ---------------------------------------------------------------------------
# Stage23Filter -- Protocol contract for Stage 23.2+ filters
# ---------------------------------------------------------------------------


class Stage23Filter(Protocol):
    """Protocol for a Stage 23 observe-only filter.

    Implementations supply a single ``evaluate`` method. Tests
    construct fakes by writing a simple class that matches the
    Protocol -- no inheritance required, no network / I/O
    library required.

    Contract semantics:

      * ``evaluate`` MUST be a pure function of its argument. It
        MUST NOT mutate the caller-supplied input, read env
        vars, make network calls, or write to disk.
      * ``evaluate`` MUST return a ``Stage23FilterResult`` whose
        ``filter_family`` is a member of ``FILTER_FAMILIES`` and
        whose ``label`` / ``data_status`` are members of the
        Stage 23 closed sets.
      * ``evaluate`` MUST emit ``UNKNOWN`` / ``INSUFFICIENT_DATA``
        / ``MISSING_INPUT`` with a ``data_status`` of
        ``PARTIAL`` / ``MISSING`` / ``UNSUPPORTED`` when the
        input cannot support a concrete label. Stage 23 is
        honest about what it does not know; ``NORMAL`` is NOT
        the default for "we don't know".
    """

    def evaluate(
        self,
        *,
        filter_input: Stage23FilterInput,
    ) -> Stage23FilterResult: ...


__all__ = [
    "Stage23Filter",
    "Stage23FilterFamily",
]
