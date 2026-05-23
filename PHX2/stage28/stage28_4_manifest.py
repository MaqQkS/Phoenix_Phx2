"""Stage 28.4 audited private Discord HTTP transport manifest.

Stage 28.4 is the audited-private-Discord-HTTP-transport substage
of Stage 28. It introduces an in-repo, redaction-safe, private-
operator-only HTTP transport primitive that future Stage 28
runner / smoke substages will inject into the existing private
Discord send path.

Stage 28.4 ships NO runner, NO retry execution, NO retry
scheduler, NO sleep / no scheduling / no backoff execution, NO
heartbeat / health snapshot, NO CLI status line, NO bounded
private session runner, NO longer-session smoke harness, NO live
smoke, NO Stage 29 enforcement, NO X / social, NO Telegram, NO
public routing, NO subscriber routing, NO paid tier routing, NO
automated trading, NO wallet / private-key / signer logic, NO
position sizing, NO trade execution, NO dashboard / HTTP control
server, and NO daemon / systemd / watchdog / autorestart service.
Stage 28.4 reads NO process environment variables; the webhook
URL is always a caller-supplied argument passed at the transport
call boundary.

The Stage 28.4 transport sends EXACTLY ONE HTTP POST per
``send_one_audited_post(...)`` call to ONE private operator
Discord webhook URL. It validates the URL against the locked
Discord https webhook regex, validates the payload against the
forbidden-field allowlist + maximum encoded size, and returns a
closed-set redaction-safe ``Stage28_4TransportResult`` carrying
only safe-to-display fields. The transport never retries, never
sleeps, never queues, never echoes the raw URL on records or
exceptions, and never captures the raw response body on the
result.

This manifest module exposes the locked Stage 28.4 schema axes
and source-file basename inventories so downstream substages
(28.5+) can pin against them without re-deriving them from the
models / transport layers.

Exposed surface:

  * ``STAGE28_4_MINOR_VERSION``               -- ``"28.4"``.
  * ``STAGE28_4_SCHEMA_VERSION``              -- locked Stage
                                                 28.4 transport-
                                                 result schema
                                                 version.
  * ``STAGE28_4_PRODUCTION_PY_BASENAMES``     -- locked Stage
                                                 28.4 production
                                                 .py basename
                                                 inventory.
  * ``STAGE28_4_TEST_BASENAMES``              -- locked Stage
                                                 28.4 test file
                                                 basename
                                                 inventory.
  * ``STAGE28_4_SCOPE_LOCKS``                 -- closed-set
                                                 tuple of Stage
                                                 28.4 scope
                                                 locks.
  * ``STAGE28_4_TRANSPORT_STATUS_VALUES``     -- closed-set
                                                 tuple of Stage
                                                 28.4 transport-
                                                 status values.
  * ``STAGE28_4_RESPONSE_BODY_STATUS_VALUES`` -- closed-set
                                                 tuple of Stage
                                                 28.4 response-
                                                 body status
                                                 values.
  * ``STAGE28_4_REDACTION_STATUS_VALUES``     -- closed-set
                                                 tuple of Stage
                                                 28.4 redaction-
                                                 status values.
  * ``STAGE28_4_SAFE_TRANSPORT_REASON_CODE_VALUES`` -- closed-set
                                                 tuple of Stage
                                                 28.4 safe
                                                 transport-reason
                                                 code values.
  * ``STAGE28_4_SEND_ATTEMPT_COUNT_VALUES``   -- closed-set
                                                 ``(0, 1)`` tuple
                                                 of admitted
                                                 send-attempt
                                                 counts.
  * ``STAGE28_4_RETRY_AFTER_MAX_SECONDS``     -- locked numeric
                                                 retry-after cap.
  * ``STAGE28_4_MAX_PAYLOAD_BYTES``           -- locked maximum
                                                 encoded JSON
                                                 payload size.

This module imports only stdlib (``typing``) plus the Stage 28.4
production models module. It does NOT import Stage 21-27
production code, does NOT import Stage 28.1 / 28.2 / 28.3a /
28.3b production code, does NOT import any network / RPC /
messaging / DB / scheduler / secrets-management library, does
NOT read the process environment, does NOT define a CLI surface,
and contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage28.audited_http_transport_models import (
    MAX_PAYLOAD_BYTES as _MAX_PAYLOAD_BYTES,
    REDACTION_STATUS_VALUES as _REDACTION_STATUS_VALUES,
    RESPONSE_BODY_STATUS_VALUES as _RESPONSE_BODY_STATUS_VALUES,
    RETRY_AFTER_MAX_SECONDS as _RETRY_AFTER_MAX_SECONDS,
    RETRY_AFTER_MIN_SECONDS as _RETRY_AFTER_MIN_SECONDS,
    SAFE_TRANSPORT_REASON_CODE_VALUES as _SAFE_TRANSPORT_REASON_CODE_VALUES,
    SEND_ATTEMPT_COUNT_VALUES as _SEND_ATTEMPT_COUNT_VALUES,
    STAGE28_4_MINOR_VERSION as _STAGE28_4_MINOR_VERSION,
    STAGE28_4_SCHEMA_VERSION as _STAGE28_4_SCHEMA_VERSION,
    TRANSPORT_STATUS_NOT_SENT_VALUES as _TRANSPORT_STATUS_NOT_SENT_VALUES,
    TRANSPORT_STATUS_SENT_VALUES as _TRANSPORT_STATUS_SENT_VALUES,
    TRANSPORT_STATUS_VALUES as _TRANSPORT_STATUS_VALUES,
)


# Re-export for downstream pin sites.
STAGE28_4_MINOR_VERSION: str = _STAGE28_4_MINOR_VERSION
STAGE28_4_SCHEMA_VERSION: str = _STAGE28_4_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Locked Stage 28.4 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_4_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "audited_http_transport_models.py",
    "audited_http_transport.py",
    "stage28_4_manifest.py",
)


STAGE28_4_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_4_audited_http_transport_models.py",
    "test_stage_28_4_audited_http_transport.py",
    "test_stage_28_4_boundaries.py",
)


# ---------------------------------------------------------------------------
# Closed-set vocabularies re-exported for downstream pinning
# ---------------------------------------------------------------------------


STAGE28_4_TRANSPORT_STATUS_VALUES: tuple[str, ...] = tuple(
    _TRANSPORT_STATUS_VALUES
)


STAGE28_4_TRANSPORT_STATUS_SENT_VALUES: tuple[str, ...] = tuple(
    _TRANSPORT_STATUS_SENT_VALUES
)


STAGE28_4_TRANSPORT_STATUS_NOT_SENT_VALUES: tuple[str, ...] = tuple(
    _TRANSPORT_STATUS_NOT_SENT_VALUES
)


STAGE28_4_RESPONSE_BODY_STATUS_VALUES: tuple[str, ...] = tuple(
    _RESPONSE_BODY_STATUS_VALUES
)


STAGE28_4_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _REDACTION_STATUS_VALUES
)


STAGE28_4_SAFE_TRANSPORT_REASON_CODE_VALUES: tuple[str, ...] = tuple(
    _SAFE_TRANSPORT_REASON_CODE_VALUES
)


STAGE28_4_SEND_ATTEMPT_COUNT_VALUES: tuple[int, ...] = tuple(
    _SEND_ATTEMPT_COUNT_VALUES
)


# ---------------------------------------------------------------------------
# Retry-after caps + payload caps re-exported
# ---------------------------------------------------------------------------


STAGE28_4_RETRY_AFTER_MAX_SECONDS: float = _RETRY_AFTER_MAX_SECONDS
STAGE28_4_RETRY_AFTER_MIN_SECONDS: float = _RETRY_AFTER_MIN_SECONDS
STAGE28_4_MAX_PAYLOAD_BYTES: int = _MAX_PAYLOAD_BYTES


# ---------------------------------------------------------------------------
# Stage 28.4 scope locks
# ---------------------------------------------------------------------------


# Stage 28.4 is the audited private Discord HTTP transport layer
# only. The following locks are declared here so a downstream
# audit can pin them without re-reading the entire substage:
STAGE28_4_SCOPE_LOCKS: tuple[str, ...] = (
    "audited-private-discord-http-transport-only scope",
    "standard-library HTTP only",
    "exactly-one-send per invocation",
    "private-operator webhook only",
    "no env reads",
    "no retry execution",
    "no sleep / no scheduling / no backoff execution",
    "no health / heartbeat snapshot",
    "no CLI status line",
    "no bounded private session runner",
    "no longer-session smoke harness",
    "no live smoke",
    "no Stage 29 enforcement",
    "no X / social",
    "no Telegram",
    "no public routing",
    "no subscriber routing",
    "no paid tier routing",
    "no automated trading",
    "no wallet / private-key / signer logic",
    "no position sizing",
    "no trade execution",
    "no dashboard / HTTP control server",
    "no daemon / systemd / watchdog / autorestart service",
)


__all__ = (
    "STAGE28_4_MINOR_VERSION",
    "STAGE28_4_SCHEMA_VERSION",
    "STAGE28_4_PRODUCTION_PY_BASENAMES",
    "STAGE28_4_TEST_BASENAMES",
    "STAGE28_4_TRANSPORT_STATUS_VALUES",
    "STAGE28_4_TRANSPORT_STATUS_SENT_VALUES",
    "STAGE28_4_TRANSPORT_STATUS_NOT_SENT_VALUES",
    "STAGE28_4_RESPONSE_BODY_STATUS_VALUES",
    "STAGE28_4_REDACTION_STATUS_VALUES",
    "STAGE28_4_SAFE_TRANSPORT_REASON_CODE_VALUES",
    "STAGE28_4_SEND_ATTEMPT_COUNT_VALUES",
    "STAGE28_4_RETRY_AFTER_MAX_SECONDS",
    "STAGE28_4_RETRY_AFTER_MIN_SECONDS",
    "STAGE28_4_MAX_PAYLOAD_BYTES",
    "STAGE28_4_SCOPE_LOCKS",
)
