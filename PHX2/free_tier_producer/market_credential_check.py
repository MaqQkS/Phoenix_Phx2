"""Mandatory bounded pre-startup validation of the paid market credential.

Exactly ONE request.  No retry loop, no backoff, no second attempt: a rejected
credential is permanent, and the 2026-07-30 canary already proved what unbounded
retrying costs (32 retries against a constant 401).

Nothing secret is read into the verdict.  The verdict carries only the HTTP
status code, a closed-set credential classification, and a fixed sanitized
reason string — never the key, the authorization header, the query string, or
the base URL.

Startup proceeds only when the provider answers HTTP 200 AND the body matches
the expected contract shape (``success`` true with a usable ``data`` object).
Any fatal classification refuses BEFORE the live epoch is armed, so the producer
never starts, no Telegram attempt is made, and the paid ledger is untouched.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from PHX2.models.market_credential import (
    MARKET_CREDENTIAL_INVALID,
    MARKET_CREDENTIAL_MISSING,
    MARKET_CREDENTIAL_SCHEMA_INVALID,
    MARKET_CREDENTIAL_UNAUTHORIZED,
    MARKET_CREDENTIAL_UNVERIFIED,
    MARKET_CREDENTIAL_VALID,
    classify_market_credential_status,
    is_fatal_market_credential_status,
)
from PHX2.stage29.birdeye_constants import BIRDEYE_PATH_PRICE

#: Canonical, non-sensitive probe mint (wrapped SOL).  Always indexed, so a
#: failure is unambiguously about the credential and never about the token.
MARKET_CREDENTIAL_PROBE_MINT = "So11111111111111111111111111111111111111112"

MARKET_CREDENTIAL_CHECK_KIND = "PHX2_MARKET_CREDENTIAL_CHECK"

_SANITIZED_REASONS = {
    MARKET_CREDENTIAL_VALID:
        "market credential authenticated and response schema valid",
    MARKET_CREDENTIAL_INVALID:
        "market credential rejected by provider (HTTP 401)",
    MARKET_CREDENTIAL_UNAUTHORIZED:
        "market credential not authorized for this endpoint (HTTP 403)",
    MARKET_CREDENTIAL_MISSING:
        "market credential is not configured",
    MARKET_CREDENTIAL_SCHEMA_INVALID:
        "market credential authenticated but response schema did not match",
    MARKET_CREDENTIAL_UNVERIFIED:
        "market credential could not be verified (transport did not complete)",
}


def _verdict(status: str, http_status: Optional[int]) -> Dict[str, Any]:
    return {
        "kind": MARKET_CREDENTIAL_CHECK_KIND,
        "credential_status": status,
        "http_status_code": http_status,
        "sanitized_reason": _SANITIZED_REASONS[status],
        "fatal": is_fatal_market_credential_status(status),
        "attempts": 1,
        "probe_mint": MARKET_CREDENTIAL_PROBE_MINT,
    }


def validate_market_credential(
    *,
    transport: Any,
    endpoint_secret: Any,
    timeout_seconds: int = 10,
    probe_mint: str = MARKET_CREDENTIAL_PROBE_MINT,
) -> Dict[str, Any]:
    """Perform the single bounded credential check and classify the outcome."""

    if endpoint_secret is None:
        return _verdict(MARKET_CREDENTIAL_MISSING, None)
    try:
        if not str(endpoint_secret.reveal_api_key() or ""):
            return _verdict(MARKET_CREDENTIAL_MISSING, None)
    except Exception:
        return _verdict(MARKET_CREDENTIAL_MISSING, None)

    try:
        result = transport.get(
            endpoint_secret=endpoint_secret,
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": str(probe_mint)},
            timeout_seconds=int(timeout_seconds),
        )
    except Exception:
        return _verdict(MARKET_CREDENTIAL_UNVERIFIED, None)

    http_status = getattr(result, "http_status_code", None)
    try:
        http_status = int(http_status) if http_status is not None else None
    except (TypeError, ValueError):
        http_status = None

    credential_status = classify_market_credential_status(http_status)
    if credential_status is not None:
        return _verdict(credential_status, http_status)

    if http_status != 200:
        # 404/429/5xx/timeouts carry no credential verdict.  They are explicitly
        # inconclusive and must not be reported as either valid or invalid.
        return _verdict(MARKET_CREDENTIAL_UNVERIFIED, http_status)

    body = getattr(result, "body", None)
    if not isinstance(body, Mapping):
        return _verdict(MARKET_CREDENTIAL_SCHEMA_INVALID, http_status)
    if body.get("success") is not True:
        return _verdict(MARKET_CREDENTIAL_SCHEMA_INVALID, http_status)
    data = body.get("data")
    if not isinstance(data, Mapping) or data.get("value") is None:
        return _verdict(MARKET_CREDENTIAL_SCHEMA_INVALID, http_status)

    return _verdict(MARKET_CREDENTIAL_VALID, http_status)


__all__ = (
    "MARKET_CREDENTIAL_CHECK_KIND",
    "MARKET_CREDENTIAL_PROBE_MINT",
    "validate_market_credential",
)
