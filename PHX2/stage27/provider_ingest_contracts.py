"""Stage 27.3 provider-ingest module-local exception hierarchy and
closed-set assertion helpers.

Stage 27.3 follows the Stage 25 / Stage 26 / Stage 27.1 / Stage
27.2 discipline: module-local exception types rooted at plain
``Exception``, NOT at a central PHX2 error registry.

Hierarchy:

    Stage27ProviderIngestError(Exception)
    ├── Stage27ProviderIngestInvalidEventError
    ├── Stage27ProviderIngestRawPayloadRejectedError
    └── Stage27UnknownProviderIngestVocabularyError

Every Stage 27.3 provider-ingest error type is engineered so that
``str()`` and ``repr()`` of an instance NEVER carries a raw
provider payload blob, a raw secret value, or a raw webhook URL.
Error messages may only reference:

  * the closed-set field name,
  * the closed-set vocabulary token kind,
  * the offending closed-set token value (which is itself a
    closed-set candidate string, not a raw payload),
  * the type-name of the offending input (when a structural shape
    failure is being reported).

The error types do NOT accept a raw provider payload blob as a
constructor argument. The caller must redact at the call site
before raising.

The module-level assertion helpers raise
``Stage27UnknownProviderIngestVocabularyError`` when given a value
outside the locked closed-set vocabulary. They are intended for
use at the composer boundary and for downstream consumers that
want to defensively re-check a closed-set token.

This module imports only stdlib (``typing``) plus Stage 27.3
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage27.provider_ingest_models import (
    COMPOSITION_REASON_VALUES,
    COMPOSITION_STATUS_VALUES,
    EVENT_KIND_VALUES,
)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class Stage27ProviderIngestError(Exception):
    """Base type for every Stage 27.3 provider-ingest violation.

    Module-local; intentionally not a subclass of any central PHX2
    error registry so the prior-stage closed code registries stay
    out of Stage 27.3's surface.
    """


class Stage27ProviderIngestInvalidEventError(
    Stage27ProviderIngestError
):
    """Raised when the adapter receives a structurally invalid event.

    The adapter is tolerant of optional / missing fields and
    represents unknown event kinds via the closed-set
    ``UNKNOWN_EVENT_KIND`` token (the composer then skips
    deterministically). This error is reserved for the case where
    the candidate is not even shaped like a normalized event
    (e.g. ``None``, a non-mapping, or a record missing the locked
    required field set).
    """

    def __init__(
        self,
        reason: str,
        *,
        offending_type_name: Optional[str] = None,
    ) -> None:
        self.reason: str = reason
        self.offending_type_name: Optional[str] = offending_type_name
        msg = f"invalid Stage 27.3 ingest event: reason={reason!r}"
        if offending_type_name is not None:
            msg += f" type={offending_type_name!r}"
        super().__init__(msg)


class Stage27ProviderIngestRawPayloadRejectedError(
    Stage27ProviderIngestError
):
    """Raised when the adapter sees a forbidden raw-payload-class field.

    Stage 27.3 explicitly refuses to admit raw provider payload
    blobs, secrets, webhook URLs, or other raw-payload-class
    content into the ingest input. The error carries only the
    offending field name (closed-set match), never the value.
    """

    def __init__(self, field_name: str) -> None:
        self.field_name: str = field_name
        super().__init__(
            f"Stage 27.3 ingest input rejected raw-payload-class "
            f"field {field_name!r}"
        )


class Stage27UnknownProviderIngestVocabularyError(
    Stage27ProviderIngestError
):
    """Raised when a closed-set token is outside the locked vocabulary.

    Carries only the closed-set kind tag and the offending token
    string. Never carries a raw payload blob.
    """

    def __init__(self, kind: str, value: str) -> None:
        self.kind: str = kind
        self.value: str = value
        super().__init__(
            f"unknown Stage 27.3 ingest vocabulary token: "
            f"kind={kind!r} value={value!r}"
        )


# ---------------------------------------------------------------------------
# Closed-set assertion helpers
# ---------------------------------------------------------------------------


def assert_event_kind(value: str) -> str:
    """Return ``value`` if it is a known ``EVENT_KIND`` token.

    Raises ``Stage27UnknownProviderIngestVocabularyError`` otherwise.
    """
    if value not in EVENT_KIND_VALUES:
        raise Stage27UnknownProviderIngestVocabularyError(
            "event_kind", value
        )
    return value


def assert_composition_status(value: str) -> str:
    """Return ``value`` if it is a known ``COMPOSITION_STATUS`` token."""
    if value not in COMPOSITION_STATUS_VALUES:
        raise Stage27UnknownProviderIngestVocabularyError(
            "composition_status", value
        )
    return value


def assert_composition_reason(value: str) -> str:
    """Return ``value`` if it is a known ``COMPOSITION_REASON`` token."""
    if value not in COMPOSITION_REASON_VALUES:
        raise Stage27UnknownProviderIngestVocabularyError(
            "composition_reason", value
        )
    return value
