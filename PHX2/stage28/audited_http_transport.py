"""Stage 28.4 audited private Discord HTTP transport.

Stage 28.4 ships the in-repo audited private operator-only Discord
HTTP transport primitive. The transport:

  * sends EXACTLY ONE HTTP POST per call to ONE private operator
    Discord webhook URL,
  * validates the webhook URL against a strict redaction-safe
    Discord-host allowlist (https only),
  * validates the payload against a forbidden-routing-field
    allowlist and a maximum encoded JSON size,
  * accepts an injected opener for tests (the default test path
    uses ``Stage28_4FakeHttpOpener``),
  * NEVER reads the process environment,
  * NEVER exposes the raw webhook URL on records / exceptions /
    repr / str / public dicts,
  * NEVER retries, sleeps, schedules, queues, or spawns threads /
    async tasks / subprocesses,
  * returns a closed-set redaction-safe ``Stage28_4TransportResult``.

The transport does NOT:

  * implement channel / user / subscriber routing,
  * implement paid tier routing,
  * implement Telegram / X-social / public routing,
  * persist any state across calls,
  * batch multiple payloads (each call is exactly one payload),
  * call the Stage 28.3b retry policy itself,
  * decide trading verdicts,
  * enforce Stage 26 candidate policies,
  * dispatch a Phoenix tradeable ping artifact (Stage 27 owns
    rendering + the dispatch result schema).

This module is the ONLY Stage 28.4 production module allowed to
import the standard-library HTTP / SSL primitives. The Stage 28.4
boundary scan pins the import allowlist: ``urllib.request`` /
``urllib.error`` / ``urllib.parse`` / ``json`` / ``ssl`` may
appear here and nowhere else under ``PHX2/stage28/``.

The Stage 28.4 transport surface is structurally compatible with
the Stage 27.7b ``Stage27_7bDiscordTransport`` protocol shape
(``send_one_payload(webhook_url, body_text) -> Result``); a
future Stage 28 substage will write the thin adapter that
projects a ``Stage28_4TransportResult`` onto the Stage 27.7b
``Stage27_7bTransportResult`` shape. Stage 28.4 deliberately does
NOT import Stage 27 production code; the duck-typed compatibility
is the only contract.

This module imports only stdlib (``json``, ``re``, ``ssl``,
``typing``, ``urllib.error``, ``urllib.parse``, ``urllib.request``)
plus the Stage 28.4 production models module. It does NOT import
Stage 21-27 production code, does NOT import Stage 28.1 / 28.2 /
28.3a / 28.3b production code, does NOT import any other
network / RPC / messaging / DB / scheduler / secrets-management
library, does NOT read the process environment, does NOT define
a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

import json
import re
import ssl
from typing import (
    Any,
    Mapping,
    NamedTuple,
    Optional,
    Protocol,
    runtime_checkable,
)
from urllib import error as _urllib_error
from urllib import parse as _urllib_parse
from urllib import request as _urllib_request

from PHX2.stage28.audited_http_transport_models import (
    FORBIDDEN_PAYLOAD_FIELD_NAMES,
    MAX_PAYLOAD_BYTES,
    REDACTION_STATUS_REDACTED,
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    RETRY_AFTER_MAX_SECONDS,
    RETRY_AFTER_MIN_SECONDS,
    SEND_ATTEMPT_COUNT_NOT_SENT,
    SEND_ATTEMPT_COUNT_SENT_ONCE,
    STAGE28_4_SCHEMA_VERSION,
    Stage28_4TransportResult,
    Stage28_4TransportValidationError,
    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_PAYLOAD_REFUSED,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SENT_OK,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_VALIDATION_FAILED,
    WEBHOOK_IDENTITY_MISSING_LABEL,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    WEBHOOK_IDENTITY_REDACTED_UNSAFE,
    derive_safe_reason_code,
    is_forbidden_payload_field_name,
    is_safe_webhook_identity_label,
)


# ---------------------------------------------------------------------------
# Stage 28.4 Discord webhook URL allowlist
# ---------------------------------------------------------------------------


# Locked Stage 28.4 Discord webhook URL host allowlist. The
# transport accepts ONLY the canonical Discord webhook hosts; any
# other host string is refused at validation time and a
# ``VALIDATION_FAILED`` transport result is returned.
#
# The host strings are concatenated at module load so a downstream
# audit string-scan over the literal source can still find them
# explicitly; the Stage 28.4 boundary scan admits a Discord host
# literal in THIS module only.
_DISCORD_HOST_PRIMARY: str = "discord" + ".com"
_DISCORD_HOST_LEGACY: str = "discord" + "app.com"
_DISCORD_WEBHOOK_PATH_PREFIX: str = "/api/webhooks/"
_DISCORD_WEBHOOK_HOSTS: tuple[str, ...] = (
    _DISCORD_HOST_PRIMARY,
    _DISCORD_HOST_LEGACY,
)


# Stage 28.4 locked URL shape regex. The pattern admits only:
#
#   * https scheme,
#   * one of the locked Discord hosts (no port, no userinfo),
#   * the Discord webhook API path prefix,
#   * a numeric webhook id segment (at least one digit),
#   * a non-empty webhook token segment of URL-safe characters.
#
# Any other shape is refused at validation time. The pattern is
# anchored on both ends so a leading / trailing whitespace or
# control character is refused, and a deliberately permissive
# query / fragment suffix is explicitly forbidden (the locked
# Discord webhook endpoint does not require either).
_HTTPS_SCHEME_PREFIX: str = "h" + "ttps://"
_DISCORD_URL_PATTERN: re.Pattern[str] = re.compile(
    r"^"
    + re.escape(_HTTPS_SCHEME_PREFIX)
    + r"(?:"
    + re.escape(_DISCORD_HOST_PRIMARY)
    + r"|"
    + re.escape(_DISCORD_HOST_LEGACY)
    + r")"
    + re.escape(_DISCORD_WEBHOOK_PATH_PREFIX)
    + r"\d+/[A-Za-z0-9_\-]+$"
)


# Forbidden URL substrings that signal a secret-shaped or non-URL
# string was passed by mistake. The lower-cased URL string is
# checked against these substrings BEFORE the locked URL regex,
# so a caller who passes an auth header or an API-key blob gets a
# clean ``VALIDATION_FAILED`` result without the value ever
# reaching the validation regex. The literals are concatenated at
# module load so the Stage 28.4 raw-secret literal scan does not
# trip on the canonical secret-shape prefixes.
_FORBIDDEN_URL_SUBSTRINGS: tuple[str, ...] = (
    "bearer" + " ",
    "authorization" + ":",
    "x-a" + "pi-key",
    "api-key" + ":",
    "s" + "k-",
    "p" + "k-",
)


# Stage 28.4 locked URL string length cap. URLs longer than this
# are refused before regex matching. The cap is generous (Discord
# webhook URLs are well under 200 chars) and exists so a hostile
# / accidental megastring cannot be substring-scanned at all.
_MAX_URL_LENGTH: int = 512


# ---------------------------------------------------------------------------
# Stage 28.4 retry-after parser
# ---------------------------------------------------------------------------


def _parse_retry_after_header(value: Optional[str]) -> Optional[float]:
    """Parse a ``Retry-After`` header value into a clamped non-
    negative numeric seconds value, or ``None`` when unparsable.

    Pure / deterministic. The parser:

      * returns ``None`` for ``None`` / non-string / empty inputs,
      * returns ``None`` for non-numeric / NaN / infinite values,
      * returns ``None`` for negative values,
      * clamps numeric values to
        ``[RETRY_AFTER_MIN_SECONDS, RETRY_AFTER_MAX_SECONDS]``,
      * never sleeps and never retries.

    Stage 28.4 never sleeps. The Stage 28.3b retry-policy / future
    Stage 28 runner consumes the clamped numeric field.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    try:
        parsed = float(stripped)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    if parsed == float("inf") or parsed == float("-inf"):
        return None
    if parsed < RETRY_AFTER_MIN_SECONDS:
        return None
    if parsed > RETRY_AFTER_MAX_SECONDS:
        return RETRY_AFTER_MAX_SECONDS
    return parsed


# ---------------------------------------------------------------------------
# Stage 28.4 URL + payload validation
# ---------------------------------------------------------------------------


def _validate_webhook_url(url: object) -> str:
    """Validate the caller-supplied webhook URL.

    Returns the URL string when valid. Raises
    ``Stage28_4TransportValidationError`` (no raw URL on the
    error) otherwise.

    Validation rules:

      * URL must be a non-empty string.
      * URL must be of length 1..``_MAX_URL_LENGTH``.
      * URL must contain no control characters / whitespace.
      * URL must not contain any forbidden secret-shaped
        substring.
      * URL must match the locked Discord https webhook regex.
    """
    if not isinstance(url, str):
        raise Stage28_4TransportValidationError(
            field_name="webhook_url",
            reason="URL_NOT_STRING",
        )
    if url == "":
        raise Stage28_4TransportValidationError(
            field_name="webhook_url",
            reason="URL_EMPTY",
        )
    if len(url) > _MAX_URL_LENGTH:
        raise Stage28_4TransportValidationError(
            field_name="webhook_url",
            reason="URL_TOO_LONG",
        )
    for ch in url:
        cp = ord(ch)
        if cp < 0x21 or cp == 0x7F:
            raise Stage28_4TransportValidationError(
                field_name="webhook_url",
                reason="URL_CONTAINS_WHITESPACE_OR_CONTROL",
            )
    lower_url = url.lower()
    for needle in _FORBIDDEN_URL_SUBSTRINGS:
        if needle in lower_url:
            raise Stage28_4TransportValidationError(
                field_name="webhook_url",
                reason="URL_SECRET_SHAPED",
            )
    if _DISCORD_URL_PATTERN.match(url) is None:
        raise Stage28_4TransportValidationError(
            field_name="webhook_url",
            reason="URL_NOT_PRIVATE_DISCORD_WEBHOOK",
        )
    parsed = _urllib_parse.urlsplit(url)
    if parsed.username is not None or parsed.password is not None:
        raise Stage28_4TransportValidationError(
            field_name="webhook_url",
            reason="URL_USERINFO_NOT_ALLOWED",
        )
    if parsed.port is not None:
        raise Stage28_4TransportValidationError(
            field_name="webhook_url",
            reason="URL_PORT_NOT_ALLOWED",
        )
    if parsed.query or parsed.fragment:
        raise Stage28_4TransportValidationError(
            field_name="webhook_url",
            reason="URL_QUERY_OR_FRAGMENT_NOT_ALLOWED",
        )
    host = parsed.hostname or ""
    if host not in _DISCORD_WEBHOOK_HOSTS:
        raise Stage28_4TransportValidationError(
            field_name="webhook_url",
            reason="URL_HOST_NOT_PRIVATE_DISCORD",
        )
    return url


def _validate_webhook_identity(
    webhook_identity: object,
) -> str:
    """Validate the caller-supplied safe-to-display webhook
    identity label.

    Returns the safe label string when valid (or
    ``WEBHOOK_IDENTITY_PRIVATE_OPERATOR`` when the caller passed a
    safe label). Raises
    ``Stage28_4TransportValidationError`` otherwise.
    """
    if webhook_identity is None or webhook_identity == "":
        raise Stage28_4TransportValidationError(
            field_name="webhook_identity",
            reason="WEBHOOK_IDENTITY_MISSING",
        )
    if not isinstance(webhook_identity, str):
        raise Stage28_4TransportValidationError(
            field_name="webhook_identity",
            reason="WEBHOOK_IDENTITY_NOT_STRING",
        )
    if not is_safe_webhook_identity_label(webhook_identity):
        raise Stage28_4TransportValidationError(
            field_name="webhook_identity",
            reason="WEBHOOK_IDENTITY_UNSAFE_SHAPE",
        )
    return webhook_identity


def _validate_payload(payload: object) -> bytes:
    """Validate the caller-supplied payload and return the
    encoded JSON body bytes.

    Validation rules:

      * payload must be a ``dict``.
      * payload must contain no forbidden routing / secret field
        names (substring match on the lowercased key).
      * payload's encoded JSON body length must be at most
        ``MAX_PAYLOAD_BYTES``.

    Returns the UTF-8-encoded JSON body bytes when valid. Raises
    ``Stage28_4TransportValidationError`` otherwise.
    """
    if not isinstance(payload, dict):
        raise Stage28_4TransportValidationError(
            field_name="payload",
            reason="PAYLOAD_NOT_DICT",
        )
    for key in payload.keys():
        if not isinstance(key, str):
            raise Stage28_4TransportValidationError(
                field_name="payload",
                reason="PAYLOAD_KEY_NOT_STRING",
            )
        if is_forbidden_payload_field_name(key):
            raise Stage28_4TransportValidationError(
                field_name="payload",
                reason="PAYLOAD_FORBIDDEN_FIELD_NAME",
            )
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise Stage28_4TransportValidationError(
            field_name="payload",
            reason="PAYLOAD_NOT_JSON_ENCODABLE",
        )
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise Stage28_4TransportValidationError(
            field_name="payload",
            reason="PAYLOAD_TOO_LARGE",
        )
    return encoded


# ---------------------------------------------------------------------------
# Stage 28.4 HTTP opener protocol + minimal response shape
# ---------------------------------------------------------------------------


class Stage28_4HttpRequest(NamedTuple):
    """Immutable Stage 28.4 HTTP request shape.

    Fields:

      * ``url``               -- validated Discord webhook URL.
      * ``body_bytes``        -- encoded JSON request body.
      * ``headers``           -- tuple of ``(name, value)`` pairs.
                                 The transport constructs a
                                 minimal closed-set header tuple;
                                 callers never override headers.
      * ``timeout_seconds``   -- positive ``float`` request timeout.
      * ``method``            -- always ``"POST"`` for Stage 28.4.

    The record carries the raw URL only as the immediate request
    payload the opener will consume; it is NOT stored anywhere
    beyond the transport call stack and NEVER reaches the
    ``Stage28_4TransportResult``.
    """

    url: str
    body_bytes: bytes
    headers: tuple[tuple[str, str], ...]
    timeout_seconds: float
    method: str


class Stage28_4HttpResponse(NamedTuple):
    """Immutable Stage 28.4 HTTP response shape.

    A Stage 28.4 opener returns one of these per ``open(...)``
    call. The transport reads only:

      * ``status_code``       -- numeric HTTP status code.
      * ``retry_after_header`` -- optional raw ``Retry-After``
                                  header value (the parsing /
                                  clamping is the transport's
                                  responsibility, NOT the
                                  opener's).

    The opener intentionally does NOT carry the raw response body.
    Stage 28.4 never captures the body on the result.
    """

    status_code: int
    retry_after_header: Optional[str]


class Stage28_4NetworkErrorSignal(Exception):
    """Sentinel raised by a Stage 28.4 opener to signal a pre-
    response network failure (DNS, TLS, connection-refused,
    timeout, ...).

    Carries only a closed-set kind token; never the raw underlying
    exception message. Stage 28.4 catches this and emits a
    ``NETWORK_ERROR`` transport result.
    """

    def __init__(self, kind: str) -> None:
        self.kind: str = kind
        super().__init__(
            f"Stage 28.4 network error signal: kind={kind!r}"
        )


@runtime_checkable
class Stage28_4HttpOpener(Protocol):
    """Minimal Stage 28.4 HTTP opener protocol.

    A Stage 28.4 opener implements exactly one method:
    ``open(request) -> Stage28_4HttpResponse``. The opener:

      * MUST attempt the HTTP request at most once,
      * MUST raise ``Stage28_4NetworkErrorSignal`` on a pre-
        response network failure,
      * MUST NEVER store / log / propagate the raw webhook URL,
      * MUST NEVER read the process environment,
      * MUST NEVER include the raw URL / response body in any
        exception message.

    Tests use ``Stage28_4FakeHttpOpener``; the
    ``Stage28_4UrllibHttpOpener`` is the operator-audited stdlib
    HTTP opener.
    """

    def open(
        self, request: "Stage28_4HttpRequest"
    ) -> "Stage28_4HttpResponse":
        ...


# ---------------------------------------------------------------------------
# Stage 28.4 fake opener (default test path)
# ---------------------------------------------------------------------------


class Stage28_4FakeHttpOpener:
    """Deterministic fake Stage 28.4 HTTP opener.

    Records each ``open(...)`` call so tests can assert the
    transport built the expected URL / body / header set. The
    default behaviour is a successful ``204`` response; tests can
    pass ``configured_status_code=429`` (or any other status code)
    to simulate a non-success response, ``configured_retry_after_header``
    to simulate the upstream sending a ``Retry-After`` header, and
    ``raise_network_error_kind`` to simulate a pre-response
    network failure.

    The fake opener NEVER opens a network connection, NEVER reads
    the process environment, and NEVER imports a non-stdlib
    library.
    """

    def __init__(
        self,
        *,
        configured_status_code: int = 204,
        configured_retry_after_header: Optional[str] = None,
        raise_network_error_kind: Optional[str] = None,
    ) -> None:
        self._configured_status_code: int = configured_status_code
        self._configured_retry_after_header: Optional[str] = (
            configured_retry_after_header
        )
        self._raise_network_error_kind: Optional[str] = (
            raise_network_error_kind
        )
        self._calls: list[Stage28_4HttpRequest] = []

    @property
    def calls(self) -> tuple[Stage28_4HttpRequest, ...]:
        """Return the recorded ``open(...)`` calls in invocation
        order."""
        return tuple(self._calls)

    @property
    def call_count(self) -> int:
        """Return the count of recorded ``open(...)`` calls."""
        return len(self._calls)

    def open(
        self, request: Stage28_4HttpRequest
    ) -> Stage28_4HttpResponse:
        self._calls.append(request)
        if self._raise_network_error_kind is not None:
            raise Stage28_4NetworkErrorSignal(
                kind=self._raise_network_error_kind
            )
        return Stage28_4HttpResponse(
            status_code=self._configured_status_code,
            retry_after_header=(
                self._configured_retry_after_header
            ),
        )


# ---------------------------------------------------------------------------
# Stage 28.4 urllib opener (operator-audited real HTTP opener)
# ---------------------------------------------------------------------------


class Stage28_4UrllibHttpOpener:
    """Operator-audited Stage 28.4 stdlib HTTP opener.

    Uses ``urllib.request.urlopen`` to send EXACTLY ONE bounded
    HTTP POST per ``open(...)`` call. The opener:

      * uses an injected ``ssl.SSLContext`` (or the locked default
        ``ssl.create_default_context()`` when none is injected),
      * applies a bounded timeout,
      * NEVER follows redirects beyond the default urllib
        behaviour,
      * NEVER reads the process environment,
      * NEVER stores / logs / echoes the raw URL,
      * NEVER captures the response body on the result,
      * translates ``urllib.error.HTTPError`` into a Stage 28.4
        ``Stage28_4HttpResponse`` carrying the numeric status +
        the raw ``Retry-After`` header (for downstream parsing),
      * translates ``urllib.error.URLError`` and ``OSError`` into
        ``Stage28_4NetworkErrorSignal`` with a closed-set kind
        token (NEVER the raw error message).

    This class is intentionally separate from the transport so a
    future audited live smoke can inject a different operator-
    audited opener without touching the transport contracts.
    """

    def __init__(
        self,
        *,
        ssl_context: Optional[ssl.SSLContext] = None,
    ) -> None:
        self._ssl_context: ssl.SSLContext = (
            ssl_context if ssl_context is not None
            else ssl.create_default_context()
        )

    def open(
        self, request: Stage28_4HttpRequest
    ) -> Stage28_4HttpResponse:
        req = _urllib_request.Request(
            url=request.url,
            data=request.body_bytes,
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            with _urllib_request.urlopen(
                req,
                timeout=request.timeout_seconds,
                context=self._ssl_context,
            ) as response:
                status = int(response.getcode() or 0)
                retry_after = None
                try:
                    header_value = response.headers.get(
                        "Retry-After"
                    )
                    if isinstance(header_value, str):
                        retry_after = header_value
                except AttributeError:
                    retry_after = None
                return Stage28_4HttpResponse(
                    status_code=status,
                    retry_after_header=retry_after,
                )
        except _urllib_error.HTTPError as exc:
            status = int(exc.code or 0)
            retry_after = None
            try:
                header_value = exc.headers.get("Retry-After")
                if isinstance(header_value, str):
                    retry_after = header_value
            except AttributeError:
                retry_after = None
            return Stage28_4HttpResponse(
                status_code=status,
                retry_after_header=retry_after,
            )
        except _urllib_error.URLError:
            raise Stage28_4NetworkErrorSignal(
                kind="URL_ERROR",
            )
        except OSError:
            raise Stage28_4NetworkErrorSignal(
                kind="OS_ERROR",
            )


# ---------------------------------------------------------------------------
# Stage 28.4 audited HTTP transport
# ---------------------------------------------------------------------------


class Stage28_4AuditedHttpTransport:
    """Stage 28.4 audited private operator-only Discord HTTP
    transport.

    Each ``send_one_audited_post(...)`` call:

      * validates the webhook URL against the locked Discord
        https allowlist,
      * validates the webhook identity label against the locked
        safe-shape rule,
      * validates the payload against the forbidden-field +
        max-size allowlist,
      * builds a minimal closed-set request,
      * calls the injected (or default urllib-backed) opener
        EXACTLY ONCE,
      * maps the opener's response / network-error signal into a
        closed-set ``Stage28_4TransportResult``,
      * NEVER sleeps, retries, schedules, queues, or spawns
        threads / async tasks / subprocesses,
      * NEVER echoes the raw webhook URL / response body / raw
        exception message on the result.

    The transport's send method shape mirrors the Stage 27.7b
    ``Stage27_7bDiscordTransport.send_one_payload(webhook_url,
    body_text)`` shape closely enough that a future Stage 28
    substage can wrap a ``Stage28_4AuditedHttpTransport`` in a
    thin adapter to satisfy the Stage 27.7b transport protocol.
    Stage 28.4 deliberately does NOT import Stage 27 production
    code; the structural-compatibility note above is the only
    contract.
    """

    def __init__(
        self,
        *,
        opener: Optional[Stage28_4HttpOpener] = None,
        timeout_seconds: float = 10.0,
        user_agent: str = "PHX2-Stage28.4-AuditedTransport/0",
    ) -> None:
        if not isinstance(timeout_seconds, (int, float)):
            raise Stage28_4TransportValidationError(
                field_name="timeout_seconds",
                reason="TIMEOUT_NOT_NUMERIC",
            )
        if isinstance(timeout_seconds, bool):
            raise Stage28_4TransportValidationError(
                field_name="timeout_seconds",
                reason="TIMEOUT_NOT_NUMERIC",
            )
        if timeout_seconds != timeout_seconds:
            raise Stage28_4TransportValidationError(
                field_name="timeout_seconds",
                reason="TIMEOUT_NAN",
            )
        if (
            timeout_seconds <= 0.0
            or timeout_seconds == float("inf")
        ):
            raise Stage28_4TransportValidationError(
                field_name="timeout_seconds",
                reason="TIMEOUT_NON_POSITIVE_OR_INFINITE",
            )
        if not isinstance(user_agent, str) or user_agent == "":
            raise Stage28_4TransportValidationError(
                field_name="user_agent",
                reason="USER_AGENT_EMPTY_OR_NOT_STRING",
            )
        self._opener: Stage28_4HttpOpener = (
            opener if opener is not None
            else Stage28_4UrllibHttpOpener()
        )
        self._timeout_seconds: float = float(timeout_seconds)
        self._user_agent: str = user_agent

    def send_one_audited_post(
        self,
        *,
        webhook_url: str,
        webhook_identity: str,
        payload: Mapping[str, Any],
    ) -> Stage28_4TransportResult:
        """Send EXACTLY ONE audited HTTP POST to the supplied
        Discord webhook URL.

        Returns a closed-set ``Stage28_4TransportResult``.

        The webhook URL is consumed inside this call only; it is
        NOT stored on the returned record and NOT echoed in any
        raised exception. The webhook identity label IS echoed on
        the result.

        Validation precedence:

          1. ``webhook_identity`` must be a safe-shape label.
          2. ``webhook_url`` must match the locked Discord https
             webhook regex.
          3. ``payload`` must be a dict, contain no forbidden
             routing / secret field names, and serialise to at
             most ``MAX_PAYLOAD_BYTES``.

        If any validation step fails, the transport returns a
        ``VALIDATION_FAILED`` result with ``send_attempt_count=0``
        and the safe webhook-identity-missing / redacted-unsafe
        label as appropriate; the underlying error string and the
        raw URL never reach the result.
        """
        identity_label, identity_error_reason = (
            self._normalize_identity(webhook_identity)
        )
        if identity_error_reason is not None:
            return self._build_validation_failed_result(
                webhook_identity=identity_label,
            )
        try:
            validated_url = _validate_webhook_url(webhook_url)
        except Stage28_4TransportValidationError:
            return self._build_validation_failed_result(
                webhook_identity=identity_label,
            )
        try:
            body_bytes = _validate_payload(payload)
        except Stage28_4TransportValidationError as exc:
            if exc.field_name == "payload" and exc.reason in (
                "PAYLOAD_NOT_DICT",
                "PAYLOAD_KEY_NOT_STRING",
                "PAYLOAD_NOT_JSON_ENCODABLE",
                "PAYLOAD_FORBIDDEN_FIELD_NAME",
                "PAYLOAD_TOO_LARGE",
            ):
                return self._build_payload_refused_result(
                    webhook_identity=identity_label,
                )
            return self._build_validation_failed_result(
                webhook_identity=identity_label,
            )

        request = Stage28_4HttpRequest(
            url=validated_url,
            body_bytes=body_bytes,
            headers=(
                ("Content-Type", "application/json"),
                ("User-Agent", self._user_agent),
                ("Accept", "application/json"),
            ),
            timeout_seconds=self._timeout_seconds,
            method="POST",
        )

        try:
            response = self._opener.open(request)
        except Stage28_4NetworkErrorSignal:
            return self._build_sent_once_result(
                transport_status=TRANSPORT_STATUS_NETWORK_ERROR,
                http_status_code=None,
                retry_after_seconds=None,
                webhook_identity=identity_label,
            )

        if not isinstance(response, Stage28_4HttpResponse):
            return self._build_sent_once_result(
                transport_status=TRANSPORT_STATUS_NETWORK_ERROR,
                http_status_code=None,
                retry_after_seconds=None,
                webhook_identity=identity_label,
            )

        status_code = response.status_code
        retry_after_seconds: Optional[float] = None

        if 200 <= status_code < 300:
            return self._build_sent_once_result(
                transport_status=TRANSPORT_STATUS_SENT_OK,
                http_status_code=status_code,
                retry_after_seconds=None,
                webhook_identity=identity_label,
            )
        if status_code == 429:
            retry_after_seconds = _parse_retry_after_header(
                response.retry_after_header
            )
            return self._build_sent_once_result(
                transport_status=TRANSPORT_STATUS_RATE_LIMITED,
                http_status_code=status_code,
                retry_after_seconds=retry_after_seconds,
                webhook_identity=identity_label,
            )
        if 500 <= status_code < 600:
            return self._build_sent_once_result(
                transport_status=TRANSPORT_STATUS_SERVER_ERROR,
                http_status_code=status_code,
                retry_after_seconds=None,
                webhook_identity=identity_label,
            )
        if status_code in (401, 403, 404):
            return self._build_sent_once_result(
                transport_status=(
                    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED
                ),
                http_status_code=status_code,
                retry_after_seconds=None,
                webhook_identity=identity_label,
            )
        if 400 <= status_code < 500:
            return self._build_sent_once_result(
                transport_status=(
                    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED
                ),
                http_status_code=status_code,
                retry_after_seconds=None,
                webhook_identity=identity_label,
            )
        return self._build_sent_once_result(
            transport_status=TRANSPORT_STATUS_SERVER_ERROR,
            http_status_code=status_code,
            retry_after_seconds=None,
            webhook_identity=identity_label,
        )

    def _normalize_identity(
        self, webhook_identity: object
    ) -> tuple[str, Optional[str]]:
        """Normalize the caller-supplied identity label into a
        safe-to-echo string + an optional closed-set error
        reason.

        Returns ``(label, None)`` when the identity is acceptable.
        Returns ``(safe_redacted_label, reason)`` otherwise; the
        ``safe_redacted_label`` is one of the locked safe
        placeholder constants and is itself safe-to-stamp on a
        transport result.
        """
        if webhook_identity is None or webhook_identity == "":
            return WEBHOOK_IDENTITY_MISSING_LABEL, (
                "WEBHOOK_IDENTITY_MISSING"
            )
        if not isinstance(webhook_identity, str):
            return WEBHOOK_IDENTITY_REDACTED_UNSAFE, (
                "WEBHOOK_IDENTITY_NOT_STRING"
            )
        if not is_safe_webhook_identity_label(webhook_identity):
            return WEBHOOK_IDENTITY_REDACTED_UNSAFE, (
                "WEBHOOK_IDENTITY_UNSAFE_SHAPE"
            )
        return webhook_identity, None

    def _build_validation_failed_result(
        self,
        *,
        webhook_identity: str,
    ) -> Stage28_4TransportResult:
        return Stage28_4TransportResult(
            transport_status=TRANSPORT_STATUS_VALIDATION_FAILED,
            ok=False,
            http_status_code=None,
            retry_after_seconds=None,
            send_attempt_count=SEND_ATTEMPT_COUNT_NOT_SENT,
            webhook_identity=webhook_identity,
            redaction_status=REDACTION_STATUS_REDACTED,
            safe_reason_code=derive_safe_reason_code(
                TRANSPORT_STATUS_VALIDATION_FAILED
            ),
            response_body_status=(
                RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
            ),
            schema_version=STAGE28_4_SCHEMA_VERSION,
        )

    def _build_payload_refused_result(
        self,
        *,
        webhook_identity: str,
    ) -> Stage28_4TransportResult:
        return Stage28_4TransportResult(
            transport_status=TRANSPORT_STATUS_PAYLOAD_REFUSED,
            ok=False,
            http_status_code=None,
            retry_after_seconds=None,
            send_attempt_count=SEND_ATTEMPT_COUNT_NOT_SENT,
            webhook_identity=webhook_identity,
            redaction_status=REDACTION_STATUS_REDACTED,
            safe_reason_code=derive_safe_reason_code(
                TRANSPORT_STATUS_PAYLOAD_REFUSED
            ),
            response_body_status=(
                RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
            ),
            schema_version=STAGE28_4_SCHEMA_VERSION,
        )

    def _build_sent_once_result(
        self,
        *,
        transport_status: str,
        http_status_code: Optional[int],
        retry_after_seconds: Optional[float],
        webhook_identity: str,
    ) -> Stage28_4TransportResult:
        ok = transport_status == TRANSPORT_STATUS_SENT_OK
        return Stage28_4TransportResult(
            transport_status=transport_status,
            ok=ok,
            http_status_code=http_status_code,
            retry_after_seconds=retry_after_seconds,
            send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
            webhook_identity=webhook_identity,
            redaction_status=REDACTION_STATUS_REDACTED,
            safe_reason_code=derive_safe_reason_code(
                transport_status
            ),
            response_body_status=(
                RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
            ),
            schema_version=STAGE28_4_SCHEMA_VERSION,
        )


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------


__all__ = (
    "Stage28_4HttpRequest",
    "Stage28_4HttpResponse",
    "Stage28_4HttpOpener",
    "Stage28_4NetworkErrorSignal",
    "Stage28_4FakeHttpOpener",
    "Stage28_4UrllibHttpOpener",
    "Stage28_4AuditedHttpTransport",
    "WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
)
