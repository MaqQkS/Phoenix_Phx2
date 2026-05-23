"""Stage 28.4 audited private Discord HTTP transport models.

Stage 28.4 ships an in-repo, audited, redaction-safe, private-
operator-only Discord HTTP transport primitive. This module ships
the immutable closed-set vocabularies + result record + exception
hierarchy + safe-label constants that the Stage 28.4 transport
implementation in ``audited_http_transport.py`` returns.

The Stage 28.4 transport answers, for a single audited private
operator-only Discord HTTP send invocation:

  * Did the single bounded HTTP POST attempt succeed?
  * If not, was it a closed-set rate-limit / server-error /
    network-error / auth-or-webhook-refused / validation-failed /
    payload-refused outcome?
  * If the upstream responded with a ``Retry-After`` header, what
    was the clamped non-negative numeric seconds value (the
    transport never sleeps; the future Stage 28 runner substage
    consumes the clamped numeric field via the Stage 28.3b retry
    policy)?
  * What safe-to-display webhook identity label should the
    dispatch result echo?
  * What closed-set redaction status applied to the captured
    surface?

Stage 28.4 is NOT a retry executor. The transport emits exactly
one transport result per call; it never sleeps, never retries,
never re-sends, never enqueues, never spawns threads / async
tasks / subprocesses. A future Stage 28 substage will own the
retry executor that consumes Stage 28.3b retry decisions over
this transport result.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No socket. No file I/O at
    import or call time.
  * No sleep. No backoff execution. No scheduling. No queue. No
    threads. No async. No subprocess.
  * No raw secret value is ever carried on a Stage 28.4 record.
    The webhook URL, the request body bytes, the response body
    bytes, the auth-header values, and the raw exception string
    are never copied onto a result; the record exposes only
    closed-set tokens + safe-to-display labels + a clamped
    numeric retry-after field + a safe snake_case reason code.
  * ``repr()`` / ``str()`` of any Stage 28.4 record is safe to
    log / print / persist; no URL host substring, no API-key
    substring, no bearer-token substring, no private webhook
    substring, and no raw exception text reaches the result
    record.

This module imports only stdlib (``typing``). It does NOT import
Stage 21-27 production code, does NOT import Stage 28.1 / 28.2 /
28.3a / 28.3b production code, does NOT import any network /
RPC / messaging / DB / scheduler / secrets-management library,
does NOT read the process environment, does NOT define a CLI
surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 28.4 version axes
# ---------------------------------------------------------------------------


STAGE28_4_MINOR_VERSION: str = "28.4"
STAGE28_4_SCHEMA_VERSION: str = "stage28_4_audited_http_transport_v0"


# Distinctive Stage 28.4 redaction token. Distinct from the Stage
# 27, Stage 28.1, Stage 28.2, Stage 28.3a, and Stage 28.3b
# redaction tokens so a leak-scan test for one cannot collide with
# another.
STAGE28_4_REDACTION_TOKEN: str = "<<STAGE28_4_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set: transport status
# ---------------------------------------------------------------------------


# Closed-set Stage 28.4 transport-status tokens. Every Stage 28.4
# transport result carries exactly one of these. Each token is a
# safe-to-log canonical label; raw HTTP status codes flow on a
# separate optional field. The set is intentionally narrow: every
# branch maps to one of these tokens, no exceptions.
TRANSPORT_STATUS_SENT_OK: str = "SENT_OK"
TRANSPORT_STATUS_RATE_LIMITED: str = "RATE_LIMITED"
TRANSPORT_STATUS_SERVER_ERROR: str = "SERVER_ERROR"
TRANSPORT_STATUS_NETWORK_ERROR: str = "NETWORK_ERROR"
TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED: str = (
    "AUTH_OR_WEBHOOK_REFUSED"
)
TRANSPORT_STATUS_VALIDATION_FAILED: str = "VALIDATION_FAILED"
TRANSPORT_STATUS_PAYLOAD_REFUSED: str = "PAYLOAD_REFUSED"


TRANSPORT_STATUS_VALUES: tuple[str, ...] = (
    TRANSPORT_STATUS_SENT_OK,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
    TRANSPORT_STATUS_VALIDATION_FAILED,
    TRANSPORT_STATUS_PAYLOAD_REFUSED,
)


# Closed-set subset: transport statuses that mean "no HTTP POST
# was actually sent". The transport uses this set to enforce
# ``send_attempt_count == 0`` on pre-send rejections.
TRANSPORT_STATUS_NOT_SENT_VALUES: tuple[str, ...] = (
    TRANSPORT_STATUS_VALIDATION_FAILED,
    TRANSPORT_STATUS_PAYLOAD_REFUSED,
)


# Closed-set subset: transport statuses that mean "the HTTP POST
# was attempted exactly once". The transport uses this set to
# enforce ``send_attempt_count == 1`` on sent-then-error paths.
TRANSPORT_STATUS_SENT_VALUES: tuple[str, ...] = (
    TRANSPORT_STATUS_SENT_OK,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
)


# ---------------------------------------------------------------------------
# Closed-set: safe reason codes
# ---------------------------------------------------------------------------


# Stage 28.4 safe reason codes are deterministic, redaction-safe
# snake_case derivations of the transport-status tokens. They are
# locked here so downstream readers can pin the set without re-
# deriving it from the transport-status tokens.
SAFE_TRANSPORT_REASON_CODE_VALUES: tuple[str, ...] = tuple(
    status.lower() for status in TRANSPORT_STATUS_VALUES
)


def is_safe_transport_reason_code_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.4
    safe-transport-reason-code token."""
    return (
        isinstance(value, str)
        and value in SAFE_TRANSPORT_REASON_CODE_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: response body status
# ---------------------------------------------------------------------------


# Closed-set Stage 28.4 response-body status tokens. The transport
# never captures the raw response body on the result record; this
# field carries only the safe closed-set marker indicating that the
# body was deliberately dropped (``DROPPED_UNRECORDED``) or that
# the underlying transport returned no body shape worth capturing
# (``NOT_CAPTURED``).
RESPONSE_BODY_STATUS_DROPPED_UNRECORDED: str = "DROPPED_UNRECORDED"
RESPONSE_BODY_STATUS_NOT_CAPTURED: str = "NOT_CAPTURED"


RESPONSE_BODY_STATUS_VALUES: tuple[str, ...] = (
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    RESPONSE_BODY_STATUS_NOT_CAPTURED,
)


def is_response_body_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.4
    response-body status token."""
    return (
        isinstance(value, str)
        and value in RESPONSE_BODY_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: redaction status
# ---------------------------------------------------------------------------


REDACTION_STATUS_REDACTED: str = "REDACTED"
REDACTION_STATUS_FAILED: str = "REDACTION_FAILED"


REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_FAILED,
)


def is_redaction_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.4
    redaction-status token."""
    return (
        isinstance(value, str) and value in REDACTION_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Webhook identity label vocabulary
# ---------------------------------------------------------------------------


# Stage 28.4 only carries a SAFE-TO-DISPLAY ``webhook_identity``
# label on the transport result. The raw URL is a function argument
# at the transport call site and is NEVER stored on the result. The
# locked private-operator label below mirrors the Stage 27.7b safe
# identity token but is intentionally redeclared here so Stage 28.4
# does NOT import Stage 27 production code.
WEBHOOK_IDENTITY_PRIVATE_OPERATOR: str = "PRIVATE_OPERATOR_WEBHOOK"


# Safe-to-display placeholder stamped onto a Stage 28.4 result
# when the caller-supplied ``webhook_identity`` is non-empty but
# fails the locked safe-identity allowlist regex (URL-shaped /
# secret-shaped / mixed-case / contains slashes or whitespace or
# dots / etc.). The literal is deliberately distinctive so a test
# scanning for the canary value of a fake webhook URL cannot
# collide with a legitimate identity label.
WEBHOOK_IDENTITY_REDACTED_UNSAFE: str = (
    "REDACTED_UNSAFE_WEBHOOK_IDENTITY"
)


# Safe-to-display placeholder stamped onto a Stage 28.4 result
# when the caller did NOT supply a webhook identity (e.g. empty
# string / non-string / ``None``). Distinct from
# ``WEBHOOK_IDENTITY_REDACTED_UNSAFE`` so an audit reader can tell
# missing-vs-unsafe apart.
WEBHOOK_IDENTITY_MISSING_LABEL: str = "MISSING_WEBHOOK_IDENTITY"


# ---------------------------------------------------------------------------
# Retry-after handling caps
# ---------------------------------------------------------------------------


# Locked Stage 28.4 retry-after cap. Any retry-after header value
# parsed by the transport is clamped to this maximum before the
# transport emits the result. Stage 28.4 never sleeps; the cap
# exists to keep a future executor's bounded wait small and to
# preserve invariance with the Stage 28.3b retry-policy cap.
RETRY_AFTER_MAX_SECONDS: float = 30.0


# Locked floor: retry-after values below the floor are treated as
# the floor. Negative / NaN / infinite parsed values are refused
# (the field is left as ``None`` on the result).
RETRY_AFTER_MIN_SECONDS: float = 0.0


# ---------------------------------------------------------------------------
# Send-attempt count limits
# ---------------------------------------------------------------------------


# Stage 28.4 transport invariant: a single transport call attempts
# at most ONE HTTP POST. The result's ``send_attempt_count`` is
# always exactly ``0`` (pre-send rejection) or ``1`` (exactly one
# POST attempted). Any other value is a Stage 28.4 invariant
# violation.
SEND_ATTEMPT_COUNT_NOT_SENT: int = 0
SEND_ATTEMPT_COUNT_SENT_ONCE: int = 1
SEND_ATTEMPT_COUNT_VALUES: tuple[int, ...] = (
    SEND_ATTEMPT_COUNT_NOT_SENT,
    SEND_ATTEMPT_COUNT_SENT_ONCE,
)


# ---------------------------------------------------------------------------
# Closed-set: forbidden payload-routing field names
# ---------------------------------------------------------------------------


# Stage 28.4 must NEVER admit a caller-supplied payload that
# carries a routing field implying audience broadening / public
# routing / subscriber routing / paid tier / trading verdict /
# enforcement / approval semantics. The transport refuses the
# payload at validation time with ``PAYLOAD_REFUSED`` rather than
# silently forwarding it.
FORBIDDEN_PAYLOAD_FIELD_NAMES: tuple[str, ...] = (
    "subscriber_id",
    "subscriber_ids",
    "channel_id",
    "channel_ids",
    "public_channel_id",
    "audience",
    "paid_tier",
    "paid_tier_id",
    "route_id",
    "routing_id",
    "approval_status",
    "approval_id",
    "enforcement_result",
    "enforcement_decision",
    "trade_side",
    "trade_direction",
    "buy_signal",
    "sell_signal",
    "position_size",
    "wallet_address",
    "signer_address",
    "private_key",
    "auth_header",
    "authorization",
    "bearer_token",
    "api_key",
    "webhook_url",
    "discord_webhook_url",
    "rpc_url",
    "telegram_chat_id",
    "x_user_id",
    "tweet_id",
)


def is_forbidden_payload_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a Stage 28.4 forbidden
    payload-routing / secret-class field name.

    Pure / deterministic. The transport uses this to reject any
    caller who tries to smuggle a public routing / enforcement /
    trade / wallet / secret field through the audited transport.
    The comparison is lower-cased + hyphen-normalised (hyphens are
    treated as underscores) and substring-based; any field whose
    normalised name contains any forbidden substring is refused.
    """
    if not isinstance(name, str):
        return False
    normalized = name.lower().replace("-", "_")
    for forbidden in FORBIDDEN_PAYLOAD_FIELD_NAMES:
        if forbidden in normalized:
            return True
    return False


# Locked maximum encoded JSON payload size in bytes. Discord's
# documented webhook content limit is well under this number;
# Stage 28.4 uses a conservative cap so accidental oversized
# payloads are refused before any HTTP POST happens.
MAX_PAYLOAD_BYTES: int = 8192


# ---------------------------------------------------------------------------
# Safe webhook-identity allowlist (matches Stage 27.7b shape)
# ---------------------------------------------------------------------------


def is_safe_webhook_identity_label(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo Stage 28.4
    webhook identity label.

    Safe identities are non-empty strings of length 1..64 made of
    ``A-Z`` / ``0-9`` / ``_`` starting with an uppercase letter.
    The shape mirrors the Stage 27.7b safe-identity rule
    deliberately so Stage 28.4 callers can reuse the same labels;
    Stage 28.4 does NOT import the Stage 27.7b helper.
    """
    if not isinstance(value, str):
        return False
    if value == "":
        return False
    if len(value) > 64:
        return False
    first = value[0]
    if not ("A" <= first <= "Z"):
        return False
    for ch in value[1:]:
        if "A" <= ch <= "Z":
            continue
        if "0" <= ch <= "9":
            continue
        if ch == "_":
            continue
        return False
    return True


# ---------------------------------------------------------------------------
# Transport result record
# ---------------------------------------------------------------------------


class Stage28_4TransportResult(NamedTuple):
    """Immutable Stage 28.4 audited private HTTP transport result.

    Closed-set / safe fields:

      * ``transport_status``        -- closed-set
                                       ``TRANSPORT_STATUS_*`` token.
      * ``ok``                      -- ``bool``; ``True`` iff
                                       ``transport_status ==
                                       SENT_OK``.
      * ``http_status_code``        -- optional numeric HTTP status
                                       code; populated when the
                                       HTTP POST was actually
                                       attempted (the
                                       ``TRANSPORT_STATUS_SENT_VALUES``
                                       subset). ``None`` on pre-
                                       send refusals + on network-
                                       error paths where the
                                       transport never saw a
                                       status line.
      * ``retry_after_seconds``     -- optional non-negative
                                       ``float`` retry-after hint;
                                       populated only when the
                                       upstream returned a parsable
                                       ``Retry-After`` header on a
                                       ``RATE_LIMITED`` outcome,
                                       clamped to
                                       ``RETRY_AFTER_MAX_SECONDS``.
                                       ``None`` otherwise. Stage
                                       28.4 NEVER sleeps; the
                                       future runner consumes this
                                       value via Stage 28.3b.
      * ``send_attempt_count``      -- always exactly ``0`` or ``1``;
                                       ``0`` on pre-send refusals,
                                       ``1`` on any path that
                                       attempted a POST.
      * ``webhook_identity``        -- safe-to-display webhook
                                       identity label (e.g.
                                       ``"PRIVATE_OPERATOR_WEBHOOK"``).
                                       NEVER a raw URL.
      * ``redaction_status``        -- closed-set Stage 28.4
                                       redaction verdict.
                                       ``REDACTED`` on the happy
                                       path.
      * ``safe_reason_code``        -- closed-set lowercase
                                       snake_case reason code;
                                       deterministically derived
                                       from ``transport_status``.
      * ``response_body_status``    -- closed-set Stage 28.4
                                       response-body status token
                                       (``DROPPED_UNRECORDED`` /
                                       ``NOT_CAPTURED``).
      * ``schema_version``          -- locked Stage 28.4 transport-
                                       result schema version.

    Excluded by construction:

      * raw webhook URL
      * webhook token / id substring
      * raw request body bytes
      * raw response body bytes
      * raw header values (auth / cookie / etc.)
      * raw exception text
      * raw network error string (e.g. resolver / socket message)
      * any caller-supplied field that may carry secret-like
        material
    """

    transport_status: str
    ok: bool
    http_status_code: Optional[int]
    retry_after_seconds: Optional[float]
    send_attempt_count: int
    webhook_identity: str
    redaction_status: str
    safe_reason_code: str
    response_body_status: str
    schema_version: str


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def is_transport_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.4
    transport-status token."""
    return (
        isinstance(value, str)
        and value in TRANSPORT_STATUS_VALUES
    )


def is_sent_transport_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is one of the closed-set
    Stage 28.4 transport statuses that imply the HTTP POST was
    attempted exactly once (i.e. ``send_attempt_count`` must be
    ``1``)."""
    return (
        isinstance(value, str)
        and value in TRANSPORT_STATUS_SENT_VALUES
    )


def is_not_sent_transport_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is one of the closed-set
    Stage 28.4 transport statuses that imply no HTTP POST was
    attempted (i.e. ``send_attempt_count`` must be ``0``)."""
    return (
        isinstance(value, str)
        and value in TRANSPORT_STATUS_NOT_SENT_VALUES
    )


def derive_safe_reason_code(transport_status: str) -> str:
    """Return the closed-set Stage 28.4 safe-reason code for the
    given transport-status token.

    Pure / deterministic. The mapping is the lowercased
    transport-status token; raising on an unknown token forces
    Stage 28.4 callers to stay inside the locked closed set.
    """
    if not is_transport_status_value(transport_status):
        raise Stage28_4TransportRedactionLeakError(
            field_name="transport_status",
            reason="TRANSPORT_STATUS_NOT_CLOSED_SET",
        )
    return transport_status.lower()


# ---------------------------------------------------------------------------
# Module-local exception hierarchy
# ---------------------------------------------------------------------------


class Stage28_4TransportError(Exception):
    """Base type for every Stage 28.4 audited HTTP transport error.

    Module-local; not a subclass of any central PHX2 error
    registry. Raw secret values must never reach the constructor;
    callers redact at the call site. Subclasses carry only closed-
    set fields + safe-to-log labels.
    """


class Stage28_4TransportValidationError(Stage28_4TransportError):
    """Raised when a caller-supplied transport argument fails the
    Stage 28.4 construction-time validation contract.

    Carries only the canonical field name + a closed-set reason
    token; never the raw rejected value. The Stage 28.4 transport
    catches this at the dispatch boundary and converts it into a
    typed ``VALIDATION_FAILED`` transport result rather than
    propagating the error.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.4 transport validation error: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_4TransportRedactionLeakError(Stage28_4TransportError):
    """Raised when an internal Stage 28.4 invariant would have let
    a non-closed-set / secret-shaped value reach a transport
    result.

    Carries only the canonical field name + a closed-set reason
    token; never the raw offending value. This exception is a
    programmer-error signal: a Stage 28.4 caller / contributor
    constructed a result with a token outside the locked closed
    set.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.4 transport redaction leak error: "
            f"field={field_name!r} reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Helper: safe headers redactor
# ---------------------------------------------------------------------------


def redacted_safe_headers(
    headers: Mapping[str, str],
) -> tuple[tuple[str, str], ...]:
    """Return a redaction-safe tuple of header pairs by dropping
    any header whose name matches a Stage 28.4 forbidden-name
    substring.

    Pure / deterministic. Stage 28.4 callers may use this helper
    when constructing the request to make sure no caller-supplied
    auth / cookie / api-key header sneaks through. The helper is
    a defence-in-depth utility; the transport itself constructs
    its own minimal header set and never echoes caller-supplied
    header VALUES anywhere.
    """
    if not isinstance(headers, Mapping):
        return ()
    out: list[tuple[str, str]] = []
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        if is_forbidden_payload_field_name(name):
            continue
        out.append((name, value))
    return tuple(out)


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------


__all__ = (
    # Version axes.
    "STAGE28_4_MINOR_VERSION",
    "STAGE28_4_SCHEMA_VERSION",
    "STAGE28_4_REDACTION_TOKEN",
    # Transport-status constants.
    "TRANSPORT_STATUS_SENT_OK",
    "TRANSPORT_STATUS_RATE_LIMITED",
    "TRANSPORT_STATUS_SERVER_ERROR",
    "TRANSPORT_STATUS_NETWORK_ERROR",
    "TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED",
    "TRANSPORT_STATUS_VALIDATION_FAILED",
    "TRANSPORT_STATUS_PAYLOAD_REFUSED",
    "TRANSPORT_STATUS_VALUES",
    "TRANSPORT_STATUS_SENT_VALUES",
    "TRANSPORT_STATUS_NOT_SENT_VALUES",
    # Response-body status.
    "RESPONSE_BODY_STATUS_DROPPED_UNRECORDED",
    "RESPONSE_BODY_STATUS_NOT_CAPTURED",
    "RESPONSE_BODY_STATUS_VALUES",
    # Redaction-status.
    "REDACTION_STATUS_REDACTED",
    "REDACTION_STATUS_FAILED",
    "REDACTION_STATUS_VALUES",
    # Webhook identity labels.
    "WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
    "WEBHOOK_IDENTITY_REDACTED_UNSAFE",
    "WEBHOOK_IDENTITY_MISSING_LABEL",
    # Retry-after caps.
    "RETRY_AFTER_MAX_SECONDS",
    "RETRY_AFTER_MIN_SECONDS",
    # Send-attempt count constants.
    "SEND_ATTEMPT_COUNT_NOT_SENT",
    "SEND_ATTEMPT_COUNT_SENT_ONCE",
    "SEND_ATTEMPT_COUNT_VALUES",
    # Forbidden payload field names.
    "FORBIDDEN_PAYLOAD_FIELD_NAMES",
    "MAX_PAYLOAD_BYTES",
    # Safe reason codes.
    "SAFE_TRANSPORT_REASON_CODE_VALUES",
    # Records.
    "Stage28_4TransportResult",
    # Validators.
    "is_transport_status_value",
    "is_sent_transport_status",
    "is_not_sent_transport_status",
    "is_response_body_status_value",
    "is_redaction_status_value",
    "is_safe_transport_reason_code_value",
    "is_safe_webhook_identity_label",
    "is_forbidden_payload_field_name",
    # Pure derivations.
    "derive_safe_reason_code",
    # Helpers.
    "redacted_safe_headers",
    # Exceptions.
    "Stage28_4TransportError",
    "Stage28_4TransportValidationError",
    "Stage28_4TransportRedactionLeakError",
)
