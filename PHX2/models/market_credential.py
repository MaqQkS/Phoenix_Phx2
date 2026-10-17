"""Centralized closed-set classification for mandatory market-data credentials.

The 2026-07-30 canary recorded ``http_calls_total=48 / http_errors=48 /
retries=32 / http_429=0``.  Every one of those was an **HTTP 401** from the paid
market provider, but nothing in the system said so:

- the endpoint classifier lumped ``400/401/403`` together as
  ``PROVIDER_REQUEST_REJECTED`` -> ``MARKET_INVALID`` -> ``PROVIDER_MALFORMED``,
  so a credential failure was reported as a malformed provider payload;
- the retry loop treated the permanent 401 as retryable and burned 32 retries;
- preflight validated only the *presence* of the key, so an invalid mandatory
  credential passed preflight and failed silently at runtime.

This module is the single vocabulary for that classification.  It is
credential-*status* only: it never holds, logs, or transports a key value.
"""

from __future__ import annotations

from typing import Optional

#: The credential authenticated and the response schema was usable.
MARKET_CREDENTIAL_VALID = "MARKET_CREDENTIAL_VALID"
#: HTTP 401 — the credential itself is rejected.
MARKET_CREDENTIAL_INVALID = "INVALID_CREDENTIAL"
#: HTTP 403 — the credential authenticated but is not authorized for the call.
MARKET_CREDENTIAL_UNAUTHORIZED = "UNAUTHORIZED_CREDENTIAL"
#: The credential is absent / not configured at all.
MARKET_CREDENTIAL_MISSING = "MISSING_CREDENTIAL"
#: Authenticated transport reached, but the body did not match the contract.
MARKET_CREDENTIAL_SCHEMA_INVALID = "CREDENTIAL_CHECK_SCHEMA_INVALID"
#: The check could not complete (timeout / transport error / 5xx).  NOT a
#: credential verdict — it is explicitly inconclusive and must not be treated
#: as either valid or invalid.
MARKET_CREDENTIAL_UNVERIFIED = "CREDENTIAL_CHECK_UNVERIFIED"

MARKET_CREDENTIAL_STATUSES = (
    MARKET_CREDENTIAL_VALID,
    MARKET_CREDENTIAL_INVALID,
    MARKET_CREDENTIAL_UNAUTHORIZED,
    MARKET_CREDENTIAL_MISSING,
    MARKET_CREDENTIAL_SCHEMA_INVALID,
    MARKET_CREDENTIAL_UNVERIFIED,
)

#: Statuses that must refuse startup when the credential is mandatory.
MARKET_CREDENTIAL_FATAL_STATUSES = (
    MARKET_CREDENTIAL_INVALID,
    MARKET_CREDENTIAL_UNAUTHORIZED,
    MARKET_CREDENTIAL_MISSING,
    MARKET_CREDENTIAL_SCHEMA_INVALID,
)

#: HTTP statuses that are permanently fatal for a credential.  Retrying these is
#: always waste: the same key will be rejected identically every time.
PERMANENT_MARKET_AUTH_STATUSES = (401, 403)


def is_permanent_market_auth_status(status: object) -> bool:
    """True only for HTTP statuses that a retry can never resolve."""

    try:
        return int(status) in PERMANENT_MARKET_AUTH_STATUSES  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def classify_market_credential_status(status: object) -> Optional[str]:
    """Map an HTTP status to its closed-set credential classification.

    Returns ``None`` for any status that carries no credential verdict, so the
    caller keeps its own (non-credential) failure handling.
    """

    try:
        code = int(status)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if code == 401:
        return MARKET_CREDENTIAL_INVALID
    if code == 403:
        return MARKET_CREDENTIAL_UNAUTHORIZED
    return None


def is_fatal_market_credential_status(value: object) -> bool:
    """True when a mandatory-credential check must refuse startup."""

    return value in MARKET_CREDENTIAL_FATAL_STATUSES


__all__ = (
    "MARKET_CREDENTIAL_VALID",
    "MARKET_CREDENTIAL_INVALID",
    "MARKET_CREDENTIAL_UNAUTHORIZED",
    "MARKET_CREDENTIAL_MISSING",
    "MARKET_CREDENTIAL_SCHEMA_INVALID",
    "MARKET_CREDENTIAL_UNVERIFIED",
    "MARKET_CREDENTIAL_STATUSES",
    "MARKET_CREDENTIAL_FATAL_STATUSES",
    "PERMANENT_MARKET_AUTH_STATUSES",
    "is_permanent_market_auth_status",
    "classify_market_credential_status",
    "is_fatal_market_credential_status",
)
