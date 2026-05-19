"""Stage 24 observe-only decoder contract surface (foundation only at 24.1).

This module ships the typed ``Protocol`` surface every Stage
24.2+ decoder must satisfy, plus the ``Stage24PrimitiveFamily``
closed-set helper that callers use to look up the family token
for a decoder without re-implementing the closed-set lookup.

Surfaces:

  * ``Stage24PrimitiveFamily`` -- closed-set helper. Wraps the
                                  ``PRIMITIVE_FAMILIES`` tuple in a
                                  namespaced class so callers can
                                  use
                                  ``Stage24PrimitiveFamily.MEMBERS``
                                  / ``.contains`` without re-deriving
                                  the membership predicate.
  * ``Stage24Decoder``         -- the ``Protocol`` every Stage 24.2+
                                  decoder satisfies. One method:
                                  ``decode(execution_input)``
                                  returns a per-decoder result
                                  record.

Design notes:

  * The Protocol is for FAKES and downstream callers. Stage 24.1
    ships NO decoder implementation; the Protocol locks the
    surface so 24.2 / 24.3 / 24.4 / 24.5 can land additively
    without shape churn.
  * Decoders are pure functions over a ``Stage24ExecutionInput``
    -- no side effects, no network calls, no env reads. The
    Protocol does not pin those invariants at the type system
    level, but the Stage 24 boundary tests assert them at the
    AST / import level.
  * Each decoder implementation is responsible for setting
    ``decoder_name`` / ``decoder_version`` / ``primitive_family``
    / ``threshold_version`` on every produced result.

This module imports only stdlib (``typing``) plus the Stage 24
constants and models. It does NOT import Stage 21 / Stage 22 /
Stage 23 modules, does NOT import any network / RPC / messaging
/ DB / scheduler / secrets-management library, does NOT read
the process environment, does NOT define a CLI surface, and
contains no top-level I/O.
"""

from __future__ import annotations

from typing import Protocol

from PHX2.stage24.constants import PRIMITIVE_FAMILIES
from PHX2.stage24.models import Stage24ExecutionInput


# ---------------------------------------------------------------------------
# Stage24PrimitiveFamily -- closed-set helper
# ---------------------------------------------------------------------------


class Stage24PrimitiveFamily:
    """Closed-set helper for the Stage 24 primitive-family tokens.

    Wraps the ``PRIMITIVE_FAMILIES`` tuple so callers can use a
    namespaced class without re-implementing membership lookup.
    Adding a member requires a contract patch to
    ``PHX2/stage24/constants.py``.
    """

    MEMBERS: tuple[str, ...] = PRIMITIVE_FAMILIES

    @classmethod
    def contains(cls, value: str) -> bool:
        return value in cls.MEMBERS


# ---------------------------------------------------------------------------
# Stage24Decoder -- Protocol contract for Stage 24.2+ decoders
# ---------------------------------------------------------------------------


class Stage24Decoder(Protocol):
    """Protocol for a Stage 24 observe-only execution-primitive decoder.

    Implementations supply three attributes / properties and a
    single ``decode`` method. Tests construct fakes by writing
    a simple class that matches the Protocol -- no inheritance
    required, no network / I/O library required.

    Required attributes / properties:

      * ``decoder_name``      -- short non-secret decoder id
                                 (e.g. ``"compute_budget_v0"``).
                                 Stable across runs.
      * ``decoder_version``   -- version string for the decoder's
                                 implementation. Bumped when the
                                 decoder logic changes.
      * ``primitive_family``  -- one of ``PRIMITIVE_FAMILIES``.
                                 Identifies which primitive family
                                 the decoder emits results for.

    Contract semantics for ``decode``:

      * ``decode`` MUST be a pure function of its argument. It
        MUST NOT mutate the caller-supplied input, read env
        vars, make network calls, or write to disk.
      * ``decode`` MUST return a per-decoder result record (e.g.
        ``Stage24ComputeBudgetResult`` /
        ``Stage24JitoTipResult`` /
        ``Stage24RouterFeeResult`` /
        ``Stage24ExecutionQualityResult``) whose
        ``primitive_family`` matches the decoder's declared
        family, and whose ``decoder_status`` / ``data_status`` /
        ``confidence_level`` / ``fee_source`` / ``route_family`` /
        ``instruction_location`` (where applicable) are members
        of the Stage 24 closed sets.
      * ``decode`` MUST emit a deterministic placeholder record
        (``decoder_status=ABSENT`` / ``UNSUPPORTED`` /
        ``NOT_APPLICABLE`` / ``DECODE_UNCONFIRMED`` /
        ``PARTIAL`` / ``DECODE_FAILED``) when it cannot
        confidently decode the primitive. Stage 24 is honest
        about what it does not know; ``DECODED`` is reserved
        for fixture-backed evidence.
      * ``decode`` MUST never coerce an unknown amount to ``0``.
        An undecoded ``amount_lamports`` / ``amount_token`` /
        ``unit_limit`` / ``unit_price_microlamports`` is ``None``;
        a real decoded zero is permitted only when the layout
        proves the zero.
    """

    decoder_name: str
    decoder_version: str
    primitive_family: str

    def decode(
        self,
        *,
        execution_input: Stage24ExecutionInput,
    ) -> object: ...


__all__ = [
    "Stage24Decoder",
    "Stage24PrimitiveFamily",
]
