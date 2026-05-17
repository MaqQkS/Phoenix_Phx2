"""Stage 21.2 fake-only private transport.

``FakePrivateTransport`` captures Stage 21.2 private-preview ping
payloads locally. It never opens a network connection, never
requires a webhook target, never reads any credential material,
and never depends on any Phoenix1 / Stage 17..20 runtime module.

Hard scope:

  * The transport is fake-only. It captures payloads into an
    in-memory list; the simulator serializes the captures to a
    file artifact via the Stage 21.2 telemetry writer.
  * The transport rejects any payload missing or carrying the
    wrong value for the locked Stage 21.2 marker fields
    (``stage`` / ``visibility`` / ``operator_only`` / ``live_mode``
    / ``dispatch_target``) at exact equality. The check uses
    ``assert_private_preview_markers`` so the rejection rule is
    identical to the one the ping builder runs.
  * The transport injects its captured-at timestamp via the
    Stage 21 ``Clock`` protocol so re-runs with the same clock
    produce byte-identical capture records.
  * The class exposes the ``IS_FAKE_ONLY`` boolean attribute so
    the boundary tests can assert the class is Stage-21-owned
    fake material.

Stage 21.2 remediation (R3 / R11e / R13)
========================================

The Stage 21.2 Codex audit found that the transport accepted
``PrivatePreviewPingPayload`` instances at face value without
re-validating the structured payload contents and without
re-hashing them. A caller with a poisoned payload-hash field
could therefore land an arbitrary structured payload into the
capture artifact. The remediation:

  * Adds ``structured_payload`` and ``recomputed_payload_hash``
    fields to ``FakeTransportCaptureRecord``.
  * Builds a canonical, deep-frozen copy of
    ``payload.structured_payload`` at capture time (sorted keys
    recursively, nested lists sorted by canonical JSON of each
    item, ``MappingProxyType`` + tuples).
  * Validates that canonical structure through the shared
    safe_content predicate (``validate_safe_payload_dict``) with
    the locked marker keys passed as ``exempt_keys`` (S1
    adjudication).
  * Canonically serializes the validated structure to UTF-8
    JSON with sorted keys + minimal separators + ``ensure_ascii=True``.
  * Computes ``sha256(canonical_bytes).hexdigest()`` as the
    recomputed payload hash.
  * Asserts the recomputed hash matches the caller's
    ``payload.payload_hash``; mismatch raises ``Stage21Error``
    ``E2170`` (``payload_hash_mismatch_at_capture``).

The capture API exposes no ``send`` / ``dispatch`` / ``publish``
/ ``transmit`` methods (verified by
``test_capture_api_exposes_no_send_dispatch_publish_transmit``).
The class attribute
``ACTUALLY_SENT_ON_NETWORK = False`` is hardcoded and pinned by
a test so a future refactor cannot silently flip the gate.
"""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, NamedTuple, Optional

from PHX2.stage21 import safe_content as _sc
from PHX2.stage21.clock import Clock, default_clock
from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.errors import Stage21Error, Stage21TelemetryError
from PHX2.stage21.ping_builder import assert_private_preview_markers
from PHX2.stage21.ping_payloads import (
    FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
    LIVE_MODE_MARKER,
    OPERATOR_ONLY_MARKER,
    PING_PAYLOAD_REQUIRED_MARKER_KEYS,
    PRIVATE_PREVIEW_VISIBILITY,
    PrivatePreviewPingPayload,
    STAGE21_2_STAGE_LABEL,
)


# ---------------------------------------------------------------------------
# Capture record + result types
# ---------------------------------------------------------------------------


class FakeTransportCaptureRecord(NamedTuple):
    """Stage 21.2 captured-payload record.

    Carries:
      * ``capture_id`` -- deterministic id derived from the
        captured ping_id, payload_hash, and capture sequence.
      * ``ping_id`` / ``candidate_id`` / ``normalized_event_id``
        -- provenance pointers from the captured ping.
      * ``mint`` / ``event_type`` / ``observed_at_utc`` -- copied
        from the captured ping.
      * ``captured_at_utc`` -- ISO-8601 UTC string from the
        injected clock.
      * ``payload_hash`` -- copied from the captured ping
        (caller-supplied).
      * ``recomputed_payload_hash`` -- Stage 21.2 remediation
        (R3): the sha256 hex of the canonical JSON of the
        re-built ``structured_payload``. The transport asserts
        ``recomputed_payload_hash == payload_hash`` before the
        record is constructed; any mismatch surfaces as
        ``Stage21Error`` (``E2170``).
      * ``stage`` / ``visibility`` / ``operator_only`` /
        ``live_mode`` / ``dispatch_target`` -- copied locked
        markers (so the artifact carries the markers explicitly).
      * ``capture_sequence`` -- the 0-indexed sequence number of
        this capture in the transport's lifetime.
      * ``structured_payload`` -- Stage 21.2 remediation (R3):
        the canonical, deep-frozen ``MappingProxyType`` view of
        ``payload.structured_payload``. The captured record
        cannot be mutated.
      * ``actually_sent_on_network`` -- locked ``False``. The
        fake transport never sends to a network; this field
        ships in the artifact so a downstream auditor can verify
        the captured record explicitly carries the locked
        Stage 21.2 invariant.
    """

    capture_id: str
    ping_id: str
    candidate_id: str
    normalized_event_id: str
    mint: str
    event_type: str
    observed_at_utc: str
    captured_at_utc: str
    payload_hash: str
    recomputed_payload_hash: str
    stage: str
    visibility: str
    operator_only: bool
    live_mode: bool
    dispatch_target: str
    capture_sequence: int
    structured_payload: Mapping[str, Any]
    actually_sent_on_network: bool

    def public_summary(self) -> dict[str, object]:
        return {
            "capture_id": self.capture_id,
            "ping_id": self.ping_id,
            "candidate_id": self.candidate_id,
            "normalized_event_id": self.normalized_event_id,
            "mint": self.mint,
            "event_type": self.event_type,
            "observed_at_utc": self.observed_at_utc,
            "captured_at_utc": self.captured_at_utc,
            "payload_hash": self.payload_hash,
            "recomputed_payload_hash": self.recomputed_payload_hash,
            "stage": self.stage,
            "visibility": self.visibility,
            "operator_only": self.operator_only,
            "live_mode": self.live_mode,
            "dispatch_target": self.dispatch_target,
            "capture_sequence": self.capture_sequence,
            "structured_payload": _to_plain(self.structured_payload),
            "actually_sent_on_network": self.actually_sent_on_network,
        }


class FakeTransportResult(NamedTuple):
    """Outcome of one ``FakePrivateTransport.capture`` call."""

    captured: bool
    rejection_reason: str
    capture_record: Optional[FakeTransportCaptureRecord]


# ---------------------------------------------------------------------------
# Stage 21.2 fake transport
# ---------------------------------------------------------------------------


# Stage-21-owned fake-only marker attribute exposed on the class.
STAGE21_FAKE_TRANSPORT_FAKE_ONLY_MARKER: bool = True

# Stage 21.2 invariant: the fake transport never sends to a
# network. The class attribute is locked at ``False`` and is
# pinned by ``test_actually_sent_on_network_is_locked_false``.
STAGE21_FAKE_TRANSPORT_ACTUALLY_SENT_ON_NETWORK: bool = False


# Locked forbidden method names. The capture API must expose
# none of these so a future refactor cannot accidentally
# introduce a real-send-shaped surface that bypasses the
# fake-only contract. Pinned by
# ``test_capture_api_exposes_no_send_dispatch_publish_transmit``.
STAGE21_FAKE_TRANSPORT_FORBIDDEN_METHOD_NAMES: tuple[str, ...] = (
    "send",
    "dispatch",
    "publish",
    "transmit",
)


def _utc_iso(now) -> str:
    """Return an ISO-8601 UTC string for a tz-aware ``datetime``.

    Stage 21.1 / 21.2 convention: ``Z`` suffix instead of
    ``+00:00`` so the artifacts are visually consistent with the
    Stage 21.1 manifest fixtures.
    """
    s = now.isoformat()
    if s.endswith("+00:00"):
        s = s[:-6] + "Z"
    return s


def _derive_capture_id(*, ping_id: str, payload_hash: str, sequence: int) -> str:
    material = f"capture|{ping_id}|{payload_hash}|{sequence}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return "cap_" + digest[:24]


# ---------------------------------------------------------------------------
# Canonical structured payload + recomputed hash (R3)
# ---------------------------------------------------------------------------


def _to_plain(value: Any) -> Any:
    """Convert mappings/tuples to plain dict/list for JSON encoding."""
    if isinstance(value, Mapping):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _canonical_json_string(payload_mapping: Mapping[str, Any]) -> str:
    """Return canonical JSON string per Stage 21.2 R3 spec.

    Locked format: ``sort_keys=True``, ``separators=(",", ":")``,
    ``ensure_ascii=True``. The ``ensure_ascii=True`` setting
    matches the R3 spec; for all currently-validated Stage 21.2
    inputs (ASCII-only per the safe_content SHORT_LABEL char-set)
    it produces byte-identical output to the
    ``ensure_ascii=False`` form used by the ping builder's
    ``_derive_payload_hash``, so the recomputed hash matches the
    caller's ``payload.payload_hash`` exactly.
    """
    return json.dumps(
        _to_plain(payload_mapping),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _build_canonical_structured_payload(
    payload: PrivatePreviewPingPayload,
) -> Mapping[str, Any]:
    """Build a canonical, deep-frozen copy of ``payload.structured_payload``.

    Canonicalization:
      * Mapping values: sort keys alphabetically; recurse on
        each value.
      * list/tuple values: recurse on each item, then sort the
        resulting items by the canonical JSON of each item.
      * Scalar leaf values (None, bool, int, float, str, bytes):
        passed through unchanged.

    Deep-freeze:
      * Mapping -> ``MappingProxyType`` over a new dict whose
        values are themselves canonicalized + deep-frozen.
      * list/tuple -> ``tuple`` whose items are themselves
        canonicalized + deep-frozen.

    The returned mapping is immutable at every nesting level:
    ``MappingProxyType`` rejects ``__setitem__`` / ``pop`` /
    ``update`` etc., and nested tuples reject assignment.
    """

    def _canonical(value: Any) -> Any:
        if isinstance(value, Mapping):
            return MappingProxyType({
                k: _canonical(value[k])
                for k in sorted(value.keys())
            })
        if isinstance(value, (list, tuple)):
            items = [_canonical(v) for v in value]
            items.sort(key=lambda item: _canonical_json_string(
                {"__sortkey__": _to_plain(item)}
            ))
            return tuple(items)
        return value

    source = payload.structured_payload
    if not isinstance(source, Mapping):
        raise Stage21Error(
            Stage21ErrorCode.E2158,
            detail=(
                "field structured_payload kind PAYLOAD "
                f"code E2158 length -1 redacted <non-str> "
                f"actual_type {type(source).__name__}"
            ),
        )
    return _canonical(source)


class FakePrivateTransport:
    """Stage 21.2 fake-only private transport.

    Construct with an optional ``Clock`` instance. Tests inject
    a ``FrozenClock`` for deterministic ``captured_at_utc``
    values; production callers leave the default in place (which
    resolves to ``SystemClock`` -- still allowed since the
    transport never reaches a real upstream).

    The transport captures payloads into an in-memory list. The
    Stage 21.2 simulator drains the list at the end of a run and
    hands the captures to the telemetry writer.
    """

    IS_FAKE_ONLY: bool = STAGE21_FAKE_TRANSPORT_FAKE_ONLY_MARKER
    ACTUALLY_SENT_ON_NETWORK: bool = (
        STAGE21_FAKE_TRANSPORT_ACTUALLY_SENT_ON_NETWORK
    )

    def __init__(self, *, clock: Optional[Clock] = None) -> None:
        self._clock: Clock = clock or default_clock()
        self._captures: list[FakeTransportCaptureRecord] = []

    @property
    def capture_count(self) -> int:
        return len(self._captures)

    def captures(self) -> tuple[FakeTransportCaptureRecord, ...]:
        return tuple(self._captures)

    def capture(self, payload: PrivatePreviewPingPayload) -> FakeTransportResult:
        """Capture ``payload`` locally if it carries the locked markers.

        The transport runs the Stage 21.2 capture flow (R3):

          1. Assert payload is ``PrivatePreviewPingPayload``.
          2. Re-assert private-preview markers
             (``assert_private_preview_markers``).
          3. Re-assert each locked marker value identity / equality.
          4. Build a canonical, deep-frozen structured payload.
          5. Validate the canonical structured payload through
             the shared ``safe_content`` predicate, with the
             locked marker keys passed as ``exempt_keys``.
          6. Canonical-JSON serialize the validated structure.
          7. Compute ``sha256(canonical_bytes).hexdigest()`` as
             the recomputed payload hash.
          8. Assert the recomputed hash equals
             ``payload.payload_hash``; mismatch raises
             ``Stage21Error`` (``E2170``).
          9. Construct ``FakeTransportCaptureRecord`` with the
             canonical structured payload and the recomputed
             hash.

        Returns a ``FakeTransportResult`` with ``captured=True``
        and the new capture record on success.
        """
        # Step 1: payload type
        if not isinstance(payload, PrivatePreviewPingPayload):
            raise Stage21TelemetryError(
                Stage21ErrorCode.E2110,
                detail=(
                    "FakePrivateTransport.capture expected "
                    "PrivatePreviewPingPayload"
                ),
            )
        # Step 2: defense-in-depth marker assertion (mirrors the
        # ping builder's pre-return assertion).
        assert_private_preview_markers(payload)

        # Step 3: belt-and-suspenders identity checks against the
        # locked marker values. The marker assertion already
        # covers these; the explicit checks here pin the locked
        # values so a future refactor that loosens the assertion
        # still fails the transport.
        if payload.stage != STAGE21_2_STAGE_LABEL:
            raise Stage21TelemetryError(
                Stage21ErrorCode.E2111,
                detail="FakePrivateTransport rejected non-Stage-21.2 payload",
            )
        if payload.visibility != PRIVATE_PREVIEW_VISIBILITY:
            raise Stage21TelemetryError(
                Stage21ErrorCode.E2111,
                detail=(
                    "FakePrivateTransport rejected payload missing "
                    "private-preview visibility marker"
                ),
            )
        if payload.operator_only is not OPERATOR_ONLY_MARKER:
            raise Stage21TelemetryError(
                Stage21ErrorCode.E2111,
                detail=(
                    "FakePrivateTransport rejected payload with non-True "
                    "operator_only marker"
                ),
            )
        if payload.live_mode is not LIVE_MODE_MARKER:
            raise Stage21TelemetryError(
                Stage21ErrorCode.E2111,
                detail=(
                    "FakePrivateTransport rejected payload with non-False "
                    "live_mode marker"
                ),
            )
        if payload.dispatch_target != FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET:
            raise Stage21TelemetryError(
                Stage21ErrorCode.E2111,
                detail=(
                    "FakePrivateTransport rejected payload routed to "
                    "non-fake-private-transport target"
                ),
            )

        # Step 4: build canonical, deep-frozen structured payload.
        canonical_structured_payload = _build_canonical_structured_payload(
            payload
        )

        # Step 5: validate the canonical structured payload via
        # the shared safe_content predicate. Marker keys are
        # passed as exempt_keys (S1 adjudication); their values
        # are exact-equality enforced by the marker assertion
        # above.
        _sc.validate_safe_payload_dict(
            canonical_structured_payload,
            field_name="structured_payload",
            exempt_keys=frozenset(PING_PAYLOAD_REQUIRED_MARKER_KEYS),
        )

        # Step 6: canonical JSON serialize.
        canonical_string = _canonical_json_string(
            canonical_structured_payload
        )
        canonical_bytes = canonical_string.encode("utf-8")

        # Step 7: recomputed payload hash.
        recomputed_payload_hash = hashlib.sha256(
            canonical_bytes
        ).hexdigest()

        # Step 8: hash-match assertion. The detail string never
        # echoes either full hash; it shows only short prefixes
        # so an audit trail is possible without leaking the
        # canonical structure to logs.
        if recomputed_payload_hash != payload.payload_hash:
            raise Stage21Error(
                Stage21ErrorCode.E2170,
                detail=(
                    "field payload_hash kind PAYLOAD_HASH code E2170 "
                    f"length 64 redacted {payload.payload_hash[:4]}..."
                    f"{payload.payload_hash[-2:]} "
                    f"recomputed_prefix {recomputed_payload_hash[:8]} "
                    f"caller_prefix {payload.payload_hash[:8]}"
                ),
            )

        # Step 9: construct record.
        sequence = len(self._captures)
        captured_at_utc = _utc_iso(self._clock.now())
        record = FakeTransportCaptureRecord(
            capture_id=_derive_capture_id(
                ping_id=payload.ping_id,
                payload_hash=payload.payload_hash,
                sequence=sequence,
            ),
            ping_id=payload.ping_id,
            candidate_id=payload.candidate_id,
            normalized_event_id=payload.normalized_event_id,
            mint=payload.mint,
            event_type=payload.event_type,
            observed_at_utc=payload.observed_at_utc,
            captured_at_utc=captured_at_utc,
            payload_hash=payload.payload_hash,
            recomputed_payload_hash=recomputed_payload_hash,
            stage=payload.stage,
            visibility=payload.visibility,
            operator_only=payload.operator_only,
            live_mode=payload.live_mode,
            dispatch_target=payload.dispatch_target,
            capture_sequence=sequence,
            structured_payload=canonical_structured_payload,
            actually_sent_on_network=(
                STAGE21_FAKE_TRANSPORT_ACTUALLY_SENT_ON_NETWORK
            ),
        )
        self._captures.append(record)
        return FakeTransportResult(
            captured=True,
            rejection_reason="",
            capture_record=record,
        )


__all__ = [
    "FakePrivateTransport",
    "FakeTransportCaptureRecord",
    "FakeTransportResult",
    "STAGE21_FAKE_TRANSPORT_ACTUALLY_SENT_ON_NETWORK",
    "STAGE21_FAKE_TRANSPORT_FAKE_ONLY_MARKER",
    "STAGE21_FAKE_TRANSPORT_FORBIDDEN_METHOD_NAMES",
]
