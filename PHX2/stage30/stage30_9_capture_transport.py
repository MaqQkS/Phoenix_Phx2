"""Stage 30.9.1 thin innermost compact-send capture transport.

The capture transport is the innermost wrapper of the existing bounded
private live compact send path. It exposes the same minimal
``send_one_audited_post(*, webhook_identity, payload)`` send surface the
Stage 28.6 bounded private runner already calls, wraps an injected inner
transport (the existing private dispatch transport), forwards the EXACT
``webhook_identity`` + ``payload`` to it unchanged, returns the inner
transport's result verbatim, and records a sanitized in-memory projection
of what was sent for the POST-SESSION Stage 30.9.1 projector.

It is built to be wired into the existing live path LATER; Stage 30.9.1
does NOT modify the existing Stage 30.4 / 30.3 / 28.9 runner / transport
code and does NOT build a new live runner.

Capture discipline (per the Stage 30.9.0 spec lock, Section 4.1):

  * forwards the payload VERBATIM to the inner transport (no mutation);
  * records the safe-shape ``webhook_identity`` (never a destination);
  * records the enriched compact payload body EXACTLY as sent (an
    immutable string snapshot of the payload ``content`` slot, so a later
    mutation of the caller's payload dict can never retroactively change a
    capture record);
  * records the sanitized inner-transport result (a closed-set status
    token read defensively; never the raw result object, never a secret);
  * records the candidate / ping ids IF present in the payload metadata;
  * returns EXACTLY the inner transport result;
  * does NO filesystem I/O, NO network of its own, and NO env read;
  * stores records in memory only, in deterministic send order.

Discipline:

  * Stdlib only (``typing``).
  * PHX2 imports: ONLY the Stage 30.9.1 bridge-models sibling (for the
    capture record + batch summary types + the ``CAPTURED`` token). It
    imports NO Stage 28 module: the inner transport + its result are
    duck-typed, so the capture transport stays decoupled from the live
    transport implementation.
  * No ``os`` (so NO ``os.environ`` / ``os.getenv`` env read), NO
    ``json`` / ``pathlib`` / filesystem, NO ``sqlite3``, NO ``zstd`` /
    compression, NO network module, NO sleep / thread / async.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Tuple

from PHX2.stage30.stage30_9_artifact_bridge_models import (
    BRIDGE_STATUS_CAPTURED,
    Stage30_9CaptureBatchSummary,
    Stage30_9CaptureRecord,
    normalize_transport_status,
)


# ---------------------------------------------------------------------------
# Capture transport error
# ---------------------------------------------------------------------------


class Stage30_9CaptureTransportError(Exception):
    """Raised when the capture transport rejects a construction-time
    argument (an inner transport without the required send method).

    Carries only the canonical field name + a closed-set reason token;
    never the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 30.9.1 capture transport rejected argument: "
            f"field={field_name!r} reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Optional payload-metadata key names (candidate / ping ids, if present)
# ---------------------------------------------------------------------------
#
# The real private compact payload is a Discord webhook payload whose body
# lives on the ``content`` slot; it does NOT normally carry candidate / ping
# ids. The capture transport records those ids ONLY when the payload mapping
# happens to expose them (defensive / optional); the authoritative
# candidate / ping ids for the projector come from the dispatch context.


_PAYLOAD_CONTENT_KEY: str = "content"
_PAYLOAD_CANDIDATE_ID_KEY: str = "candidate_id"
_PAYLOAD_PING_ID_KEY: str = "ping_id"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _opt_str(value: object) -> Optional[str]:
    """Return ``value`` when it is a non-empty string, else ``None``."""
    return value if isinstance(value, str) and value != "" else None


def _payload_body_text(payload: object) -> Optional[str]:
    """Return the payload's ``content`` body string (an immutable snapshot)
    when the payload is a mapping whose ``content`` is a string, else
    ``None``. Strings are immutable, so the captured value can never be
    retroactively mutated by a later change to the payload mapping.
    """
    if isinstance(payload, Mapping):
        value = payload.get(_PAYLOAD_CONTENT_KEY)
        if isinstance(value, str):
            return value
    return None


def _payload_keys(payload: object) -> Tuple[str, ...]:
    """Return the sorted tuple of string keys in the payload mapping (an
    immutable snapshot), else an empty tuple. Provenance only.
    """
    if isinstance(payload, Mapping):
        return tuple(
            sorted(key for key in payload.keys() if isinstance(key, str))
        )
    return ()


def _payload_metadata_id(payload: object, key: str) -> Optional[str]:
    """Return ``payload[key]`` as a non-empty string when the payload is a
    mapping carrying that metadata id, else ``None``.
    """
    if isinstance(payload, Mapping):
        return _opt_str(payload.get(key))
    return None


def _sanitized_transport_status(result: object) -> str:
    """Return the inner transport result's status as a CLOSED-SET sanitized
    token, read defensively.

    Duck-typed: reads only the ``transport_status`` attribute, then
    normalizes it through ``normalize_transport_status`` so the stored
    value is ALWAYS one of the Stage 30.9-owned closed-set sanitized status
    tokens (a recognized live status is preserved verbatim; an
    unrecognized / blank / non-string status becomes
    ``UNKNOWN_TRANSPORT_STATUS``). It NEVER copies the raw result object
    onto a capture record and NEVER reads any other (possibly sensitive)
    attribute, so no secret-bearing field of the inner result can leak into
    a capture record. Pure; never raises.
    """
    return normalize_transport_status(
        getattr(result, "transport_status", None)
    )


# ---------------------------------------------------------------------------
# Capture transport
# ---------------------------------------------------------------------------


class Stage30_9CaptureTransport:
    """Stage 30.9.1 thin innermost compact-send capture transport.

    Construction binds an injected inner transport that MUST expose a
    callable ``send_one_audited_post`` (duck-typed; the real
    ``Stage28_9PrivateWebhookTransport`` satisfies it, as does a fake test
    transport). Each ``send_one_audited_post(*, webhook_identity, payload)``
    call:

      1. records a sanitized capture record (a fresh immutable snapshot of
         the body text + payload keys + the metadata ids, plus the
         webhook identity and the eventual sanitized status);
      2. forwards the EXACT ``webhook_identity`` + ``payload`` to the inner
         transport (no copy, no mutation);
      3. records the inner result's sanitized status onto the just-built
         capture record;
      4. returns the inner transport result VERBATIM.

    The capture record's body snapshot is taken BEFORE forwarding, from the
    payload's ``content`` string (an immutable value), so a caller that
    later mutates its payload dict cannot retroactively change a recorded
    body. Records accumulate in memory only, in send order.
    """

    __slots__ = ("_inner_transport", "_records")

    def __init__(self, *, inner_transport: object) -> None:
        if not callable(
            getattr(inner_transport, "send_one_audited_post", None)
        ):
            raise Stage30_9CaptureTransportError(
                field_name="inner_transport",
                reason="MISSING_SEND_ONE_AUDITED_POST_METHOD",
            )
        self._inner_transport: object = inner_transport
        self._records: List[Stage30_9CaptureRecord] = []

    @property
    def records(self) -> Tuple[Stage30_9CaptureRecord, ...]:
        """Return the capture records in deterministic send order."""
        return tuple(self._records)

    @property
    def capture_count(self) -> int:
        """Return the number of capture records recorded."""
        return len(self._records)

    def batch_summary(self) -> Stage30_9CaptureBatchSummary:
        """Return a passive ``CAPTURED`` batch summary of the recorded
        capture records (for offline proof composition / tests).
        """
        return Stage30_9CaptureBatchSummary(
            status=BRIDGE_STATUS_CAPTURED,
            capture_count=len(self._records),
            records=tuple(self._records),
        )

    def send_one_audited_post(
        self,
        *,
        webhook_identity: str,
        payload: Mapping[str, Any],
    ) -> object:
        """Record a sanitized capture of this send, forward the exact
        ``webhook_identity`` + ``payload`` to the inner transport, record
        the inner result's sanitized status, and return the inner result
        VERBATIM.

        The payload is forwarded unchanged (no copy, no mutation). An
        inner-transport exception propagates verbatim AFTER the pre-send
        capture record has been recorded (the record's sanitized status
        stays ``None`` in that case), so the capture trail reflects exactly
        what was attempted.
        """
        capture_index = len(self._records)
        record = Stage30_9CaptureRecord(
            capture_index=capture_index,
            webhook_identity=_opt_str(webhook_identity),
            payload_body_text=_payload_body_text(payload),
            payload_keys=_payload_keys(payload),
            sanitized_transport_status=None,
            candidate_id=_payload_metadata_id(
                payload, _PAYLOAD_CANDIDATE_ID_KEY
            ),
            ping_id=_payload_metadata_id(payload, _PAYLOAD_PING_ID_KEY),
        )
        self._records.append(record)

        result = self._inner_transport.send_one_audited_post(
            webhook_identity=webhook_identity,
            payload=payload,
        )

        # Stamp the sanitized inner-result status onto the record (frozen
        # dataclasses are immutable, so replace the stored record with an
        # updated copy carrying the closed-set status token only).
        self._records[capture_index] = Stage30_9CaptureRecord(
            capture_index=record.capture_index,
            webhook_identity=record.webhook_identity,
            payload_body_text=record.payload_body_text,
            payload_keys=record.payload_keys,
            sanitized_transport_status=_sanitized_transport_status(result),
            candidate_id=record.candidate_id,
            ping_id=record.ping_id,
        )
        return result


__all__ = (
    "Stage30_9CaptureTransportError",
    "Stage30_9CaptureTransport",
)
