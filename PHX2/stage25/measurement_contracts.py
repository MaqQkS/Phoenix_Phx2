"""Stage 25 observe-only measurement contract surface (foundation only at 25.1).

This module ships the typed ``Protocol`` surfaces every Stage
25.2+ measurer / reconciler / projector must satisfy, plus the
closed-set helper classes callers use to look up the family /
status / kind tokens without re-implementing the membership
predicate.

Surfaces:

  * ``Stage25MeasurementFamily``      -- closed-set helper wrapping
                                         ``MEASUREMENT_FAMILIES``.
  * ``Stage25SourceFamily``           -- closed-set helper wrapping
                                         ``SOURCE_FAMILIES``.
  * ``Stage25PriceWindowKind``        -- closed-set helper wrapping
                                         ``PRICE_WINDOW_KINDS``.
  * ``Stage25ATHCandidateKind``       -- closed-set helper wrapping
                                         ``ATH_CANDIDATE_KINDS``.
  * ``Stage25MigrationMeasurer``      -- ``Protocol`` for a future
                                         migration-boundary measurer.
                                         Takes a
                                         ``Stage25MeasurementInput``
                                         and returns a
                                         ``Stage25MigrationMeasurement``.
  * ``Stage25ATHReconciler``          -- ``Protocol`` for a future
                                         ATH reconciler. Takes the
                                         migration measurement plus
                                         the price observations and
                                         returns an
                                         ``Stage25ATHMeasurement``.
  * ``Stage25PriceObservationProjector``
                                      -- ``Protocol`` for a future
                                         per-observation window
                                         projector. Takes a
                                         ``Stage25PriceObservation``
                                         plus a migration measurement
                                         and returns a
                                         ``Stage25PriceWindowObservation``.

Design notes:

  * The Protocols are for FAKES and downstream callers. Stage 25.1
    ships NO measurer / reconciler / projector implementation; the
    Protocols lock the surface so 25.2 / 25.3 / 25.4 can land
    additively without shape churn.
  * Each Protocol-conforming callable is a pure function over its
    inputs -- no side effects, no network calls, no env reads. The
    Protocols do not pin those invariants at the type system level,
    but the Stage 25 boundary tests assert them at the AST / import
    level.
  * Each implementation is responsible for setting
    ``measurer_name`` / ``measurer_version`` /
    ``threshold_version`` on every produced record.

This module imports only stdlib (``typing``) plus the Stage 25
constants and models. It does NOT import Stage 21 / Stage 22 /
Stage 23 / Stage 24 production modules, does NOT import any
network / RPC / messaging / DB / scheduler / secrets-management
library, does NOT read the process environment, does NOT define
a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import Protocol

from PHX2.stage25.constants import (
    ATH_CANDIDATE_KINDS,
    MEASUREMENT_FAMILIES,
    PRICE_WINDOW_KINDS,
    SOURCE_FAMILIES,
)
from PHX2.stage25.models import (
    Stage25ATHMeasurement,
    Stage25MeasurementInput,
    Stage25MigrationMeasurement,
    Stage25PriceObservation,
    Stage25PriceWindowObservation,
)


# ---------------------------------------------------------------------------
# Closed-set helper classes
# ---------------------------------------------------------------------------


class Stage25MeasurementFamily:
    """Closed-set helper for Stage 25 ``MEASUREMENT_FAMILIES`` tokens.

    Wraps the ``MEASUREMENT_FAMILIES`` tuple so callers can use a
    namespaced class without re-implementing membership lookup.
    Adding a member requires a contract patch to
    ``PHX2/stage25/constants.py``.
    """

    MEMBERS: tuple[str, ...] = MEASUREMENT_FAMILIES

    @classmethod
    def contains(cls, value: str) -> bool:
        return value in cls.MEMBERS


class Stage25SourceFamily:
    """Closed-set helper for Stage 25 ``SOURCE_FAMILIES`` tokens."""

    MEMBERS: tuple[str, ...] = SOURCE_FAMILIES

    @classmethod
    def contains(cls, value: str) -> bool:
        return value in cls.MEMBERS


class Stage25PriceWindowKind:
    """Closed-set helper for Stage 25 ``PRICE_WINDOW_KINDS`` tokens."""

    MEMBERS: tuple[str, ...] = PRICE_WINDOW_KINDS

    @classmethod
    def contains(cls, value: str) -> bool:
        return value in cls.MEMBERS


class Stage25ATHCandidateKind:
    """Closed-set helper for Stage 25 ``ATH_CANDIDATE_KINDS`` tokens."""

    MEMBERS: tuple[str, ...] = ATH_CANDIDATE_KINDS

    @classmethod
    def contains(cls, value: str) -> bool:
        return value in cls.MEMBERS


# ---------------------------------------------------------------------------
# Stage25MigrationMeasurer
# ---------------------------------------------------------------------------


class Stage25MigrationMeasurer(Protocol):
    """Protocol for a Stage 25 observe-only migration-boundary measurer.

    Implementations supply three attributes / properties and a
    single ``measure`` method. Tests construct fakes by writing a
    simple class that matches the Protocol -- no inheritance
    required, no network / I/O library required.

    Required attributes / properties:

      * ``measurer_name``     -- short non-secret measurer id
                                 (e.g. ``"migration_measurer_v0"``).
                                 Stable across runs.
      * ``measurer_version``  -- version string for the measurer's
                                 implementation. Bumped when the
                                 measurer logic changes.
      * ``measurement_family`` -- always ``"MIGRATION"``.

    Contract semantics for ``measure``:

      * ``measure`` MUST be a pure function of its argument. It
        MUST NOT mutate the caller-supplied input, read env
        vars, make network calls, or write to disk.
      * ``measure`` MUST return a
        ``Stage25MigrationMeasurement`` whose
        ``measurement_family`` equals ``"MIGRATION"`` and whose
        ``measurement_status`` / ``confidence_level`` are members
        of the Stage 25 closed sets.
      * ``measure`` MUST emit a deterministic placeholder record
        (``measurement_status=MISSING`` / ``UNSUPPORTED`` /
        ``AMBIGUOUS`` / ``SOURCE_CONFLICT`` / ``REJECTED`` /
        ``NOT_APPLICABLE``) when the migration boundary cannot
        be confidently consolidated.
      * ``measure`` MUST never coerce an unknown slot or block
        time to ``0``; the ``-1`` sentinel records "absent."
    """

    measurer_name: str
    measurer_version: str
    measurement_family: str

    def measure(
        self,
        *,
        measurement_input: Stage25MeasurementInput,
    ) -> Stage25MigrationMeasurement: ...


# ---------------------------------------------------------------------------
# Stage25ATHReconciler
# ---------------------------------------------------------------------------


class Stage25ATHReconciler(Protocol):
    """Protocol for a Stage 25 observe-only ATH reconciler.

    Required attributes / properties:

      * ``measurer_name``     -- short non-secret reconciler id.
      * ``measurer_version``  -- version string.
      * ``measurement_family`` -- always ``"ATH"``.

    Contract semantics for ``reconcile``:

      * ``reconcile`` MUST be a pure function of its arguments. It
        MUST NOT mutate inputs, read env vars, make network calls,
        or write to disk.
      * ``reconcile`` MUST return a ``Stage25ATHMeasurement``
        whose ``measurement_family`` equals ``"ATH"`` and whose
        ``measurement_status`` / ``confidence_level`` are members
        of the Stage 25 closed sets.
      * ``reconcile`` MUST refuse to emit ``MEASURED`` when the
        upstream migration measurement carries the ``AMBIGUOUS``
        status (the post-migration window cannot be defined
        without a known boundary).
      * ``reconcile`` MUST never coerce an unknown peak price to
        ``0``; ``None`` records "no peak observed."
    """

    measurer_name: str
    measurer_version: str
    measurement_family: str

    def reconcile(
        self,
        *,
        measurement_input: Stage25MeasurementInput,
        migration_measurement: Stage25MigrationMeasurement,
    ) -> Stage25ATHMeasurement: ...


# ---------------------------------------------------------------------------
# Stage25PriceObservationProjector
# ---------------------------------------------------------------------------


class Stage25PriceObservationProjector(Protocol):
    """Protocol for a Stage 25 observe-only per-observation window projector.

    Required attributes / properties:

      * ``projector_name``    -- short non-secret projector id.
      * ``projector_version`` -- version string.

    Contract semantics for ``project``:

      * ``project`` MUST be a pure function of its arguments. It
        MUST NOT mutate inputs, read env vars, make network calls,
        or write to disk.
      * ``project`` MUST return a
        ``Stage25PriceWindowObservation`` whose ``window_kind`` is
        a member of ``PRICE_WINDOW_KINDS``.
      * ``project`` MUST emit ``window_kind=UNKNOWN_WINDOW`` when
        the upstream migration measurement carries the
        ``AMBIGUOUS`` status; the projector MUST NOT silently
        assign a window in that case.
    """

    projector_name: str
    projector_version: str

    def project(
        self,
        *,
        price_observation: Stage25PriceObservation,
        migration_measurement: Stage25MigrationMeasurement,
    ) -> Stage25PriceWindowObservation: ...


__all__ = [
    "Stage25ATHCandidateKind",
    "Stage25ATHReconciler",
    "Stage25MeasurementFamily",
    "Stage25MigrationMeasurer",
    "Stage25PriceObservationProjector",
    "Stage25PriceWindowKind",
    "Stage25SourceFamily",
]
