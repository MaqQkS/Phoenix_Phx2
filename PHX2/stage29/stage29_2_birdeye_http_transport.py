"""Stage 29.2 Birdeye HTTP transport boundary.

This module is the SINGLE Stage 29.2 surface that opens an
outbound HTTPS connection. Every other Stage 29.2 production
module stays network-free.

The transport:

  * builds a ``GET`` request to the operator-supplied Birdeye
    base URL + a locked Stage-29.2-pinned endpoint path,
  * injects exactly three HTTP headers (``X-API-KEY``,
    ``x-chain: solana``, ``accept: application/json``) plus a
    fixed Stage 29.2 user-agent,
  * applies a finite bounded timeout (from the Stage 29.2
    runtime config),
  * parses the response body as JSON,
  * returns a closed-shape result record carrying the HTTP
    status code, the parsed body (or ``None`` on parse failure),
    the closed-set Stage 29.2 refusal-reason token, and the
    client-clock ``fetched_at_utc`` timestamp.

The transport NEVER:

  * sends a request body (Stage 29.2 makes only ``GET`` calls),
  * follows a redirect to a host outside the operator-supplied
    base URL,
  * echoes the raw API key, raw base URL, raw response body, or
    raw HTTP traceback to any log / repr / exception / record,
  * retries on failure (the probe orchestrator owns retry policy
    -- which at Stage 29.2 is "no retries").

Stage 29.2 admits ``urllib.request`` + ``urllib.parse`` +
``urllib.error`` (stdlib only) in this module + the probe
module. No third-party HTTP client is admitted (no ``requests``,
no ``httpx``, no ``aiohttp``).

This module imports stdlib (``contextlib`` / ``datetime`` /
``json`` / ``typing`` / ``urllib.error`` / ``urllib.parse`` /
``urllib.request``) plus the Stage 29.2 constants + models +
readiness modules. It does NOT import:

  * Stage 21-28 production code,
  * any PHX1 / legacy Phoenix-1 source tree module,
  * any third-party HTTP / messaging / wallet / trading / Discord
    / Telegram / X library,
  * ``os`` / the process environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_ACCEPT_VALUE_JSON,
    BIRDEYE_ALLOWED_PATHS,
    BIRDEYE_HEADER_ACCEPT,
    BIRDEYE_HEADER_X_API_KEY,
    BIRDEYE_HEADER_X_CHAIN,
    BIRDEYE_HTTP_METHOD_GET,
    BIRDEYE_USER_AGENT,
    BIRDEYE_X_CHAIN_VALUE_SOLANA,
    is_safe_timeout_seconds,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
    BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_HTTP_SUCCESS_FALSE,
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
    Stage29_2BirdeyeError,
    is_birdeye_refusal_reason_value,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)


# ---------------------------------------------------------------------------
# Stage 29.2 HTTP transport result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_2BirdeyeHttpResult:
    """Immutable result of one Stage 29.2 outbound HTTP request.

    Carries closed-set tokens + the parsed JSON body dict (or
    ``None``). The raw response body is NEVER stored. The raw
    HTTP traceback is NEVER stored. The raw API key / base URL
    is NEVER copied onto this record.

    Fields:

      * ``refusal_reason`` -- closed-set Stage 29.2 refusal
        token. ``NONE`` when the request succeeded AND the
        upstream ``success`` flag (when present) was truthy.
      * ``http_status_code`` -- integer HTTP status code; ``0``
        when no response was received.
      * ``body`` -- the parsed JSON top-level dict, or ``None``
        when parsing failed / no response was received.
      * ``fetched_at_utc`` -- ISO-8601 UTC string of the
        client-clock moment when the response was received
        (Stage 29.2 NEVER uses the upstream timestamp here).
    """

    refusal_reason: str
    http_status_code: int
    body: Optional[dict]
    fetched_at_utc: str

    def __post_init__(self) -> None:
        _validate_http_result(self)


def _validate_http_result(
    record: "Stage29_2BirdeyeHttpResult",
) -> None:
    if not is_birdeye_refusal_reason_value(
        record.refusal_reason
    ):
        raise Stage29_2BirdeyeError(
            "REFUSAL_REASON_NOT_CLOSED_SET"
        )
    if (
        isinstance(record.http_status_code, bool)
        or not isinstance(record.http_status_code, int)
        or record.http_status_code < 0
    ):
        raise Stage29_2BirdeyeError("HTTP_STATUS_CODE_UNSAFE")
    if record.body is not None and not isinstance(
        record.body, dict
    ):
        raise Stage29_2BirdeyeError("BODY_TYPE_INVALID")
    if not isinstance(record.fetched_at_utc, str):
        raise Stage29_2BirdeyeError(
            "FETCHED_AT_UTC_NOT_STR"
        )


# ---------------------------------------------------------------------------
# Stage 29.2 transport Protocol (injectable; tests pass a fake)
# ---------------------------------------------------------------------------


class Stage29_2BirdeyeHttpTransport(Protocol):
    """Injectable Stage 29.2 HTTP transport boundary.

    Real production wiring uses ``Stage29_2BirdeyeUrlibTransport``
    (defined below). Tests inject a deterministic fake. The
    Protocol method NEVER raises -- every upstream failure is
    projected to a closed-set refusal token on the returned
    result record.
    """

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        ...


# ---------------------------------------------------------------------------
# Stage 29.2 stdlib urllib transport (production implementation)
# ---------------------------------------------------------------------------


class Stage29_2BirdeyeUrlibTransport:
    """Stdlib-only Stage 29.2 HTTP transport implementation.

    Uses ``urllib.request.urlopen`` exclusively. NEVER follows
    redirects to a host outside the operator-supplied base URL
    (Stage 29.2 builds the URL once and ``urllib`` is configured
    to allow only the resolved host). No third-party HTTP client
    is used.

    Stage 29.2 is read-only via this transport: only ``GET``
    requests are allowed; the method is not exposed as a
    parameter.
    """

    def __init__(self) -> None:
        # No mutable state; the transport is stateless.
        pass

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        if path not in BIRDEYE_ALLOWED_PATHS:
            return _build_error_result(
                refusal_reason=(
                    BIRDEYE_REFUSAL_REASON_HTTP_FAILED
                ),
                http_status_code=0,
            )
        if not is_safe_timeout_seconds(timeout_seconds):
            return _build_error_result(
                refusal_reason=(
                    BIRDEYE_REFUSAL_REASON_HTTP_FAILED
                ),
                http_status_code=0,
            )
        try:
            raw_base = endpoint_secret.reveal_base_url()
            raw_key = endpoint_secret.reveal_api_key()
        except Stage29_2BirdeyeError:
            return _build_error_result(
                refusal_reason=(
                    BIRDEYE_REFUSAL_REASON_HTTP_FAILED
                ),
                http_status_code=0,
            )
        url = (
            raw_base + path + "?" + urlencode(dict(query_params))
        )
        request = Request(
            url,
            method=BIRDEYE_HTTP_METHOD_GET,
        )
        request.add_header(BIRDEYE_HEADER_X_API_KEY, raw_key)
        request.add_header(
            BIRDEYE_HEADER_X_CHAIN,
            BIRDEYE_X_CHAIN_VALUE_SOLANA,
        )
        request.add_header(
            BIRDEYE_HEADER_ACCEPT, BIRDEYE_ACCEPT_VALUE_JSON
        )
        request.add_header("User-Agent", BIRDEYE_USER_AGENT)
        try:
            response = urlopen(request, timeout=timeout_seconds)
        except HTTPError as e:
            # 4xx / 5xx response from Birdeye.
            return _build_error_result(
                refusal_reason=(
                    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED
                ),
                http_status_code=int(getattr(e, "code", 0) or 0),
            )
        except URLError as e:
            # Includes socket.timeout instances on this Python.
            reason = getattr(e, "reason", None)
            if (
                reason is not None
                and "timed out" in str(reason).lower()
            ):
                return _build_error_result(
                    refusal_reason=(
                        BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT
                    ),
                    http_status_code=0,
                )
            return _build_error_result(
                refusal_reason=(
                    BIRDEYE_REFUSAL_REASON_HTTP_FAILED
                ),
                http_status_code=0,
            )
        except (
            TimeoutError,
            OSError,
        ):
            return _build_error_result(
                refusal_reason=(
                    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT
                ),
                http_status_code=0,
            )

        with response:
            status_code = int(
                getattr(response, "status", 0) or 0
            )
            raw_bytes = response.read()
        fetched_at = _iso_utc_now()
        body = _parse_json_body(raw_bytes)
        if body is None:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=(
                    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED
                ),
                http_status_code=status_code,
                body=None,
                fetched_at_utc=fetched_at,
            )
        if status_code < 200 or status_code >= 300:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=(
                    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED
                ),
                http_status_code=status_code,
                body=body,
                fetched_at_utc=fetched_at,
            )
        success_flag = body.get("success")
        if isinstance(success_flag, bool) and not success_flag:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=(
                    BIRDEYE_REFUSAL_REASON_HTTP_SUCCESS_FALSE
                ),
                http_status_code=status_code,
                body=body,
                fetched_at_utc=fetched_at,
            )
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=status_code,
            body=body,
            fetched_at_utc=fetched_at,
        )


def _parse_json_body(raw_bytes: object) -> Optional[dict]:
    """Parse ``raw_bytes`` as a JSON top-level dict. Return
    ``None`` if parsing fails OR the top-level shape is not a
    dict. The raw bytes / decoded text NEVER leave this helper.
    """
    if not isinstance(raw_bytes, (bytes, bytearray)):
        return None
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except (UnicodeDecodeError, AttributeError):
        return None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _iso_utc_now() -> str:
    """Return the client-clock UTC now as an ISO-8601 string.

    The transport intentionally uses the client clock (not the
    upstream ``data.updateUnixTime``). Tests that need a pinned
    clock should inject a deterministic transport fake instead
    of monkeypatching ``datetime``.
    """
    return datetime.now(timezone.utc).isoformat()


def _build_error_result(
    *,
    refusal_reason: str,
    http_status_code: int,
) -> Stage29_2BirdeyeHttpResult:
    return Stage29_2BirdeyeHttpResult(
        refusal_reason=refusal_reason,
        http_status_code=http_status_code,
        body=None,
        fetched_at_utc=_iso_utc_now(),
    )


__all__ = (
    "Stage29_2BirdeyeHttpResult",
    "Stage29_2BirdeyeHttpTransport",
    "Stage29_2BirdeyeUrlibTransport",
)
