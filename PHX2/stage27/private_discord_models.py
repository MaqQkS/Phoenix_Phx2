"""Stage 27.7b private Discord dispatch model layer.

Stage 27.7b ships the in-memory model layer for the controlled
private operator-only Discord smoke dispatch boundary. Every model
in this module is a frozen ``NamedTuple`` so the entire Stage 27.7b
substage can pass these records around without any mutable global
state, and so ``repr()`` / ``str()`` of any record never carries a
raw webhook URL value -- because no field on any of these records
is ever populated with a raw webhook URL value in the first place.

Stage 27.7b deliberately does NOT:

  * call Discord at module import (the sender takes a transport
    argument, never a hardcoded webhook host),
  * import any network / RPC / messaging library,
  * read the process environment,
  * implement channel / user / subscriber routing,
  * implement paid tiers,
  * implement public routing,
  * implement Telegram or X / social transport,
  * enforce Stage 26 candidate policies,
  * decide trading verdicts,
  * promote UNKNOWN / DISAGREE / USDC into the existing-SOL
    calibration lane,
  * persist any state across dispatches.

Closed-set vocabularies:

  * ``DISPATCH_STATUS``   -- ``SENT`` / ``DRY_RUN_NOT_SENT`` /
                             ``REFUSED_NOT_LIVE`` /
                             ``REFUSED_MISSING_WEBHOOK`` /
                             ``REFUSED_MULTIPLE_PAYLOADS`` /
                             ``REFUSED_SUPPRESSED_PAIR`` /
                             ``REFUSED_UNAUTHORIZED_MODE`` /
                             ``TRANSPORT_ERROR``
  * ``DISPATCH_REASON``   -- closed-set reason codes describing
                             how the dispatch verdict was reached.
  * ``DISPATCH_MODE``     -- ``DRY_RUN`` / ``LIVE_SEND``.
  * ``REDACTION_STATUS``  -- ``REDACTED`` / ``REDACTION_FAILED``.

The dispatch result record carries only closed-set tokens, safe-to-
display canonical fields, the upstream provenance IDs, and the
safe-to-display webhook identity label. No field on the record
ever takes a raw webhook URL, a raw API key, a raw RPC URL, a
secret canary, or a raw provider payload blob.

This module imports only stdlib (``re`` / ``typing``). It does NOT
import Stage 21-26 production code, does NOT import Stage 27.1
production code, does NOT import any network / RPC / messaging /
DB / scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 27.7b version axes
# ---------------------------------------------------------------------------


STAGE27_7B_MINOR_VERSION: str = "27.7b"
STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION: str = (
    "stage27_v0_private_discord_dispatch_result"
)


# ---------------------------------------------------------------------------
# dispatch_status closed set
# ---------------------------------------------------------------------------
#
# SENT                          -- transport accepted the payload and
#                                  returned a non-error status.
# DRY_RUN_NOT_SENT              -- dispatch ran in DRY_RUN mode; the
#                                  transport was NOT called.
# REFUSED_NOT_LIVE              -- live_mode_authority did not resolve
#                                  to LIVE_ALLOWED.
# REFUSED_MISSING_WEBHOOK       -- webhook identity or webhook URL was
#                                  missing / empty.
# REFUSED_MULTIPLE_PAYLOADS     -- caller tried to send more than one
#                                  payload in a single dispatch.
# REFUSED_SUPPRESSED_PAIR       -- pair classification refuses live
#                                  send (UNKNOWN / DISAGREE always;
#                                  USDC without OBSERVE_ONLY warning).
# REFUSED_UNAUTHORIZED_MODE     -- operator_live_request or
#                                  smoke_dispatch_request flag was
#                                  not set, or dispatch_mode was an
#                                  unknown token.
# TRANSPORT_ERROR               -- transport raised or returned an
#                                  error-shaped status.


DISPATCH_STATUS_SENT: str = "SENT"
DISPATCH_STATUS_DRY_RUN_NOT_SENT: str = "DRY_RUN_NOT_SENT"
DISPATCH_STATUS_REFUSED_NOT_LIVE: str = "REFUSED_NOT_LIVE"
DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK: str = (
    "REFUSED_MISSING_WEBHOOK"
)
DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS: str = (
    "REFUSED_MULTIPLE_PAYLOADS"
)
DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR: str = (
    "REFUSED_SUPPRESSED_PAIR"
)
DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE: str = (
    "REFUSED_UNAUTHORIZED_MODE"
)
DISPATCH_STATUS_TRANSPORT_ERROR: str = "TRANSPORT_ERROR"


DISPATCH_STATUS_VALUES: tuple[str, ...] = (
    DISPATCH_STATUS_SENT,
    DISPATCH_STATUS_DRY_RUN_NOT_SENT,
    DISPATCH_STATUS_REFUSED_NOT_LIVE,
    DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK,
    DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS,
    DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR,
    DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE,
    DISPATCH_STATUS_TRANSPORT_ERROR,
)


# A subset that represents "did not actually send to Discord". The
# dispatch layer uses this to decide whether a transport_status_code
# should be populated on the result record.
DISPATCH_STATUS_NOT_SENT_VALUES: tuple[str, ...] = (
    DISPATCH_STATUS_DRY_RUN_NOT_SENT,
    DISPATCH_STATUS_REFUSED_NOT_LIVE,
    DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK,
    DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS,
    DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR,
    DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE,
)


# ---------------------------------------------------------------------------
# dispatch_reason closed set
# ---------------------------------------------------------------------------


DISPATCH_REASON_LIVE_SEND_OK: str = "LIVE_SEND_OK"
DISPATCH_REASON_DRY_RUN_MODE: str = "DRY_RUN_MODE"
DISPATCH_REASON_LIVE_AUTHORITY_NOT_ALLOWED: str = (
    "LIVE_AUTHORITY_NOT_ALLOWED"
)
DISPATCH_REASON_OPERATOR_LIVE_REQUEST_MISSING: str = (
    "OPERATOR_LIVE_REQUEST_MISSING"
)
DISPATCH_REASON_SMOKE_DISPATCH_REQUEST_MISSING: str = (
    "SMOKE_DISPATCH_REQUEST_MISSING"
)
DISPATCH_REASON_UNKNOWN_DISPATCH_MODE: str = (
    "UNKNOWN_DISPATCH_MODE"
)
DISPATCH_REASON_WEBHOOK_URL_MISSING: str = "WEBHOOK_URL_MISSING"
DISPATCH_REASON_WEBHOOK_IDENTITY_MISSING: str = (
    "WEBHOOK_IDENTITY_MISSING"
)
DISPATCH_REASON_WEBHOOK_IDENTITY_UNSAFE: str = (
    "WEBHOOK_IDENTITY_UNSAFE"
)
DISPATCH_REASON_MULTIPLE_PAYLOADS_REFUSED: str = (
    "MULTIPLE_PAYLOADS_REFUSED"
)
DISPATCH_REASON_NO_PAYLOAD_PROVIDED: str = "NO_PAYLOAD_PROVIDED"
DISPATCH_REASON_PAIR_SUPPRESS_UNKNOWN: str = (
    "PAIR_SUPPRESS_UNKNOWN"
)
DISPATCH_REASON_PAIR_SUPPRESS_DISAGREE: str = (
    "PAIR_SUPPRESS_DISAGREE"
)
DISPATCH_REASON_PAIR_USDC_REQUIRES_OBSERVE_ONLY: str = (
    "PAIR_USDC_REQUIRES_OBSERVE_ONLY"
)
DISPATCH_REASON_PAIR_USDC_REQUIRES_OBSERVE_ONLY_LANE: str = (
    "PAIR_USDC_REQUIRES_OBSERVE_ONLY_LANE"
)
DISPATCH_REASON_PAIR_SOL_NOT_ON_EXISTING_LANE: str = (
    "PAIR_SOL_NOT_ON_EXISTING_LANE"
)
DISPATCH_REASON_TRANSPORT_EXCEPTION: str = "TRANSPORT_EXCEPTION"
DISPATCH_REASON_TRANSPORT_NON_SUCCESS: str = (
    "TRANSPORT_NON_SUCCESS"
)


DISPATCH_REASON_VALUES: tuple[str, ...] = (
    DISPATCH_REASON_LIVE_SEND_OK,
    DISPATCH_REASON_DRY_RUN_MODE,
    DISPATCH_REASON_LIVE_AUTHORITY_NOT_ALLOWED,
    DISPATCH_REASON_OPERATOR_LIVE_REQUEST_MISSING,
    DISPATCH_REASON_SMOKE_DISPATCH_REQUEST_MISSING,
    DISPATCH_REASON_UNKNOWN_DISPATCH_MODE,
    DISPATCH_REASON_WEBHOOK_URL_MISSING,
    DISPATCH_REASON_WEBHOOK_IDENTITY_MISSING,
    DISPATCH_REASON_WEBHOOK_IDENTITY_UNSAFE,
    DISPATCH_REASON_MULTIPLE_PAYLOADS_REFUSED,
    DISPATCH_REASON_NO_PAYLOAD_PROVIDED,
    DISPATCH_REASON_PAIR_SUPPRESS_UNKNOWN,
    DISPATCH_REASON_PAIR_SUPPRESS_DISAGREE,
    DISPATCH_REASON_PAIR_USDC_REQUIRES_OBSERVE_ONLY,
    DISPATCH_REASON_PAIR_USDC_REQUIRES_OBSERVE_ONLY_LANE,
    DISPATCH_REASON_PAIR_SOL_NOT_ON_EXISTING_LANE,
    DISPATCH_REASON_TRANSPORT_EXCEPTION,
    DISPATCH_REASON_TRANSPORT_NON_SUCCESS,
)


# ---------------------------------------------------------------------------
# dispatch_mode closed set
# ---------------------------------------------------------------------------


DISPATCH_MODE_DRY_RUN: str = "DRY_RUN"
DISPATCH_MODE_LIVE_SEND: str = "LIVE_SEND"


DISPATCH_MODE_VALUES: tuple[str, ...] = (
    DISPATCH_MODE_DRY_RUN,
    DISPATCH_MODE_LIVE_SEND,
)


# ---------------------------------------------------------------------------
# redaction_status closed set
# ---------------------------------------------------------------------------


REDACTION_STATUS_REDACTED: str = "REDACTED"
REDACTION_STATUS_FAILED: str = "REDACTION_FAILED"


REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_FAILED,
)


# ---------------------------------------------------------------------------
# Webhook identity label vocabulary
# ---------------------------------------------------------------------------
#
# Stage 27.7b separates the SAFE-TO-DISPLAY ``webhook_identity``
# label (e.g. ``"private-operator-channel"``) from the raw
# ``webhook_url`` value. The raw URL is passed as a function argument
# at the dispatch boundary and is NEVER stored on the dispatch result
# record. The label is the only webhook-identifying string admitted
# onto the dispatch result.


WEBHOOK_IDENTITY_PRIVATE_OPERATOR: str = "PRIVATE_OPERATOR_WEBHOOK"


# Safe-to-display placeholder stamped onto a dispatch result when
# the caller-supplied ``webhook_identity`` is non-empty but fails
# the locked safe-identity allowlist regex (URL-shaped /
# secret-shaped / mixed-case / contains slashes or whitespace or
# dots / etc.). The literal is deliberately distinctive so a test
# scanning for the canary value of a fake webhook URL cannot
# collide with a legitimate identity label, and so an audit log
# reviewer can see that the dispatch suppressed an unsafe input.
WEBHOOK_IDENTITY_REDACTED_UNSAFE: str = (
    "REDACTED_UNSAFE_WEBHOOK_IDENTITY"
)


# ---------------------------------------------------------------------------
# Safe-identity allowlist regex
# ---------------------------------------------------------------------------
#
# Stage 27.7b webhook identity labels are short ALL_CAPS_WITH_UNDERSCORES
# tokens such as ``PRIVATE_OPERATOR_WEBHOOK``. The locked allowlist
# regex below rejects:
#
#   * URL-shaped strings (lowercase letters, slashes, colons, dots),
#   * the audit canary substring (mixed case, hyphens, digits),
#   * bearer / API / RPC / private-key markers (mixed case, spaces),
#   * leading / trailing whitespace,
#   * any string that does not start with an uppercase letter,
#   * any string longer than 64 characters,
#
# and admits identifier-like labels of length 1..64 made of
# ``A-Z`` / ``0-9`` / ``_`` starting with an uppercase letter.


_SAFE_WEBHOOK_IDENTITY_PATTERN: re.Pattern[str] = re.compile(
    r"^[A-Z][A-Z0-9_]{0,63}$"
)


def is_safe_webhook_identity(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo Stage 27.7b webhook identity.

    Safe identities are non-empty strings that match the locked
    allowlist regex ``^[A-Z][A-Z0-9_]{0,63}$``.

    Pure / deterministic. Stage 27.7b dispatch + sender both call
    this helper before stamping a caller-provided identity onto a
    dispatch result record; URL-shaped, secret-shaped, mixed-case,
    hyphen-containing, whitespace-containing, dot-containing, or
    slash-containing values fail the regex and are unsafe.

    A non-string input or an empty string returns ``False`` (the
    caller treats those as the separate ``WEBHOOK_IDENTITY_MISSING``
    refusal path, NOT as an unsafe-shape refusal).
    """
    if not isinstance(value, str):
        return False
    if value == "":
        return False
    return _SAFE_WEBHOOK_IDENTITY_PATTERN.match(value) is not None


def is_unsafe_webhook_identity(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty string that
    fails the locked safe-identity allowlist regex.

    Pure / deterministic. The Stage 27.7b dispatch + sender use this
    helper to detect URL-shaped / secret-shaped identities that
    must be rejected before any transport call and that must NEVER
    be echoed onto a dispatch result.

    Empty / non-string inputs return ``False`` because those are
    classified as ``WEBHOOK_IDENTITY_MISSING`` rather than
    ``WEBHOOK_IDENTITY_UNSAFE``.
    """
    if not isinstance(value, str):
        return False
    if value == "":
        return False
    return _SAFE_WEBHOOK_IDENTITY_PATTERN.match(value) is None


# ---------------------------------------------------------------------------
# Immutable record: dispatch result
# ---------------------------------------------------------------------------


class Stage27_7bDispatchResultRecord(NamedTuple):
    """Immutable Stage 27.7b dispatch result.

    Carries only closed-set tokens, safe-to-display canonical fields,
    upstream provenance IDs, and the safe-to-display webhook
    identity label. NEVER carries a raw webhook URL, raw API key,
    raw RPC URL, or raw provider payload blob.

    Fields:

      * ``dispatch_status``       -- closed-set Stage 27.7b dispatch
                                     status token.
      * ``dispatch_reason``       -- closed-set Stage 27.7b dispatch
                                     reason code.
      * ``dispatch_mode``         -- closed-set Stage 27.7b
                                     ``DISPATCH_MODE`` token; mirrors
                                     the mode the caller asked for.
      * ``webhook_identity``      -- caller-supplied safe-to-display
                                     webhook identity label (e.g.
                                     ``"PRIVATE_OPERATOR_WEBHOOK"``).
                                     NEVER a raw URL.
      * ``ping_id``               -- echo of the Stage 27.5 payload
                                     ``ping_id``; ``"<no_payload>"``
                                     literal when the dispatch
                                     refused before a payload could
                                     be inspected (multiple-payloads
                                     refusal / no-payload refusal).
      * ``run_id``                -- caller-supplied run identifier;
                                     ``None`` when not attached.
      * ``session_id``            -- caller-supplied session
                                     identifier; ``None`` when not
                                     attached.
      * ``sent_at_utc``           -- ISO-8601 UTC wall time supplied
                                     by the injected Stage 27.7b
                                     dispatch clock. Stamped even on
                                     refusals so the audit log shows
                                     when the decision was made.
      * ``transport_status_code`` -- numeric transport status when
                                     the transport was called;
                                     ``None`` for every dispatch
                                     status in
                                     ``DISPATCH_STATUS_NOT_SENT_VALUES``.
      * ``redaction_status``      -- closed-set Stage 27.7b redaction
                                     verdict. ``REDACTED`` on the
                                     happy path.
      * ``schema_version``        -- locked Stage 27.7b dispatch
                                     result schema version.
      * ``pair_quote_asset``      -- echo of the Stage 27.5 payload
                                     ``quote_asset`` token. Stamped
                                     for audit so the result tells
                                     the reviewer which pair class
                                     was dispatched / refused.
                                     ``"<no_payload>"`` literal when
                                     the dispatch refused before a
                                     payload could be inspected.
      * ``render_status``         -- echo of the Stage 27.5 payload
                                     ``render_status`` token. Same
                                     ``"<no_payload>"`` rule.
    """

    dispatch_status: str
    dispatch_reason: str
    dispatch_mode: str
    webhook_identity: str
    ping_id: str
    run_id: Optional[str]
    session_id: Optional[str]
    sent_at_utc: str
    transport_status_code: Optional[int]
    redaction_status: str
    schema_version: str
    pair_quote_asset: str
    render_status: str


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 27.7b must never accept a field named anything secret-class
# or raw-payload-class on its dispatch result record. The
# ``NamedTuple`` schema above already excludes such fields; this
# helper is kept so a future refactor cannot silently widen the
# admitted field set.


FORBIDDEN_DISPATCH_RESULT_FIELD_NAMES: tuple[str, ...] = (
    "raw_payload",
    "raw_payload_blob",
    "payload_blob",
    "secret",
    "api_key",
    "apikey",
    "token_secret",
    "webhook_url",
    "discord_webhook_url",
    "rpc_url",
    "private_key",
    "credentials",
    "bearer_token",
    "authorization_header",
)


def is_forbidden_dispatch_result_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden dispatch-result field name.

    Pure / deterministic. Stage 27.7b uses this to reject any caller
    who tries to smuggle a raw webhook URL / secret / payload blob
    into the dispatch result record.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_DISPATCH_RESULT_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Sentinel literals
# ---------------------------------------------------------------------------


# When the dispatch refuses before a payload can be inspected (the
# multi-payload refusal or the empty-collection refusal), the result
# record stamps these literals on the ``ping_id`` / ``pair_quote_asset``
# / ``render_status`` fields. The literals are deliberately distinctive
# so a test scanning for the canary value of a fake payload cannot
# collide with a legitimate Stage 27.5 payload field value.
NO_PAYLOAD_SENTINEL: str = "<no_payload>"
