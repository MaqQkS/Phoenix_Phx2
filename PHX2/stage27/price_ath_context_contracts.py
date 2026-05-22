"""Stage 27.4 measurement-context module-local exception hierarchy
and closed-set assertion helpers.

Stage 27.4 follows the Stage 25 / Stage 26 / Stage 27.1 / Stage
27.2 / Stage 27.3 discipline: module-local exception types rooted
at plain ``Exception``, NOT at a central PHX2 error registry.

Hierarchy:

    Stage27MeasurementContextError(Exception)
    ├── Stage27PriceSourceError
    ├── Stage27AthSourceError
    ├── Stage27MigrationSourceError
    └── Stage27UnknownMeasurementContextVocabularyError

Every Stage 27.4 measurement-context error type is engineered so
that ``str()`` and ``repr()`` of an instance NEVER carries a raw
provider payload blob, a raw secret value, or a raw webhook URL.
Error messages may only reference:

  * the closed-set field name,
  * the closed-set vocabulary token kind,
  * the offending closed-set token value (which is itself a
    closed-set candidate string, not a raw payload),
  * the closed-set source-error reason code (e.g.
    ``SOURCE_FAILED``).

The error types do NOT accept a raw provider payload blob as a
constructor argument. The caller must redact at the call site
before raising.

This module imports only stdlib (``typing``) plus Stage 27.4
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_VALUES,
    MIGRATION_SOURCE_VALUES,
    MIGRATION_STATUS_VALUES,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_REASON_VALUES,
    ATH_SINCE_MIGRATION_STATUS_VALUES,
    ATH_STATUS_VALUES,
    ATH_UNIT_VALUES,
    DRAWDOWN_BASIS_VALUES,
    PRICE_REASON_VALUES,
    PRICE_STATUS_VALUES,
    PRICE_UNIT_VALUES,
)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class Stage27MeasurementContextError(Exception):
    """Base type for every Stage 27.4 measurement-context violation.

    Module-local; intentionally not a subclass of any central PHX2
    error registry so the prior-stage closed code registries stay
    out of Stage 27.4's surface.
    """


class Stage27PriceSourceError(Stage27MeasurementContextError):
    """Raised when the injected price-context source fails or returns
    a structurally invalid snapshot.

    Carries only the closed-set source-error reason code and an
    optional safe-to-display source label. Never carries a raw
    provider payload blob or secret.
    """

    def __init__(
        self,
        reason: str,
        *,
        source_label: Optional[str] = None,
    ) -> None:
        self.reason: str = reason
        self.source_label: Optional[str] = source_label
        msg = (
            f"Stage 27.4 price source failure: reason={reason!r}"
        )
        if source_label is not None:
            msg += f" source={source_label!r}"
        super().__init__(msg)


class Stage27AthSourceError(Stage27MeasurementContextError):
    """Raised when the injected ATH-context source fails or returns
    a structurally invalid snapshot.

    Same redaction discipline as ``Stage27PriceSourceError``.
    """

    def __init__(
        self,
        reason: str,
        *,
        source_label: Optional[str] = None,
    ) -> None:
        self.reason: str = reason
        self.source_label: Optional[str] = source_label
        msg = f"Stage 27.4 ATH source failure: reason={reason!r}"
        if source_label is not None:
            msg += f" source={source_label!r}"
        super().__init__(msg)


class Stage27MigrationSourceError(
    Stage27MeasurementContextError
):
    """Raised when the injected migration-context source fails or
    returns a structurally invalid snapshot.

    Same redaction discipline as ``Stage27PriceSourceError``.
    """

    def __init__(
        self,
        reason: str,
        *,
        source_label: Optional[str] = None,
    ) -> None:
        self.reason: str = reason
        self.source_label: Optional[str] = source_label
        msg = (
            f"Stage 27.4 migration source failure: reason={reason!r}"
        )
        if source_label is not None:
            msg += f" source={source_label!r}"
        super().__init__(msg)


class Stage27UnknownMeasurementContextVocabularyError(
    Stage27MeasurementContextError
):
    """Raised when a closed-set token is outside the locked vocabulary.

    Carries only the closed-set kind tag and the offending token
    string. Never carries a raw payload blob.
    """

    def __init__(self, kind: str, value: str) -> None:
        self.kind: str = kind
        self.value: str = value
        super().__init__(
            f"unknown Stage 27.4 measurement-context vocabulary "
            f"token: kind={kind!r} value={value!r}"
        )


# ---------------------------------------------------------------------------
# Closed-set assertion helpers: price
# ---------------------------------------------------------------------------


def assert_price_status(value: str) -> str:
    """Return ``value`` if it is a known ``PRICE_STATUS`` token."""
    if value not in PRICE_STATUS_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "price_status", value
        )
    return value


def assert_price_unit(value: str) -> str:
    """Return ``value`` if it is a known ``PRICE_UNIT`` token."""
    if value not in PRICE_UNIT_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "price_unit", value
        )
    return value


def assert_price_reason(value: str) -> str:
    """Return ``value`` if it is a known ``PRICE_REASON`` token."""
    if value not in PRICE_REASON_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "price_reason", value
        )
    return value


# ---------------------------------------------------------------------------
# Closed-set assertion helpers: ATH
# ---------------------------------------------------------------------------


def assert_ath_status(value: str) -> str:
    """Return ``value`` if it is a known ``ATH_STATUS`` token."""
    if value not in ATH_STATUS_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "ath_status", value
        )
    return value


def assert_ath_unit(value: str) -> str:
    """Return ``value`` if it is a known ``ATH_UNIT`` token."""
    if value not in ATH_UNIT_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "ath_unit", value
        )
    return value


def assert_ath_since_migration_status(value: str) -> str:
    """Return ``value`` if it is a known
    ``ATH_SINCE_MIGRATION_STATUS`` token.
    """
    if value not in ATH_SINCE_MIGRATION_STATUS_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "ath_since_migration_status", value
        )
    return value


def assert_ath_reason(value: str) -> str:
    """Return ``value`` if it is a known ``ATH_REASON`` token."""
    if value not in ATH_REASON_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "ath_reason", value
        )
    return value


def assert_drawdown_basis(value: str) -> str:
    """Return ``value`` if it is a known ``DRAWDOWN_BASIS`` token."""
    if value not in DRAWDOWN_BASIS_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "drawdown_basis", value
        )
    return value


# ---------------------------------------------------------------------------
# Closed-set assertion helpers: migration
# ---------------------------------------------------------------------------


def assert_migration_status(value: str) -> str:
    """Return ``value`` if it is a known ``MIGRATION_STATUS`` token."""
    if value not in MIGRATION_STATUS_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "migration_status", value
        )
    return value


def assert_migration_reason(value: str) -> str:
    """Return ``value`` if it is a known ``MIGRATION_REASON`` token."""
    if value not in MIGRATION_REASON_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "migration_reason", value
        )
    return value


def assert_migration_source(value: str) -> str:
    """Return ``value`` if it is a known ``MIGRATION_SOURCE`` token."""
    if value not in MIGRATION_SOURCE_VALUES:
        raise Stage27UnknownMeasurementContextVocabularyError(
            "migration_source", value
        )
    return value
