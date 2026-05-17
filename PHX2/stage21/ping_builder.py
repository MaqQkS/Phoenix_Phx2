"""Stage 21.2 candidate and ping-payload builder.

Pure functions that take a ``NormalizedLiveEvent`` and produce a
``PrivatePreviewCandidate``, then take a candidate and produce a
``PrivatePreviewPingPayload``.

The builder is the seam where Stage 21.2 enforces the locked
private-preview marker invariants on every outgoing ping:

  * ``stage`` must equal ``STAGE21_2_STAGE_LABEL`` (``"21.2"``).
  * ``visibility`` must equal ``PRIVATE_PREVIEW_VISIBILITY``
    (``"private_preview"``).
  * ``operator_only`` must be Python ``True``.
  * ``live_mode`` must be Python ``False``.
  * ``dispatch_target`` must equal
    ``FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET``
    (``"fake_private_transport"``).

Any drift -- missing field, wrong type, truthy-but-not-True
marker, public/subscriber/paid routing attempt -- raises
``Stage21TelemetryError`` before the ping reaches the fake
transport or the artifact writer.

Stage 21.2 builder invariants:

  * No alert_decisions read.
  * No PHX2.db / PHX2.repositories import.
  * No filter evaluation, no ATH logic, no execution-fee logic.
  * No public / paid / subscriber routing concept.
"""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from PHX2.stage21 import safe_content as _sc
from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.errors import Stage21TelemetryError
from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage21.ping_payloads import (
    FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
    LIVE_MODE_MARKER,
    OPERATOR_ONLY_MARKER,
    PING_PAYLOAD_REQUIRED_MARKER_KEYS,
    PING_PAYLOAD_REQUIRED_MARKER_VALUES,
    PING_PAYLOAD_SCHEMA_VERSION,
    PRIVATE_PREVIEW_VISIBILITY,
    PrivatePreviewCandidate,
    PrivatePreviewPingPayload,
    STAGE21_2_STAGE_LABEL,
)


# ---------------------------------------------------------------------------
# Locked Stage 21.2 candidate / ping sources
# ---------------------------------------------------------------------------


CANDIDATE_SOURCE_DEFAULT: str = "stage21_fake_provider_normalized"
CANDIDATE_REASON_DEFAULT: str = "stage21_2_fake_event_promotion"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _canonical_json(payload: object) -> str:
    return json.dumps(
        _to_plain(payload),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _to_plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _sha256_hex(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _derive_candidate_id(event: NormalizedLiveEvent, *, reason: str, source: str) -> str:
    material = _canonical_json({
        "event_id": event.event_id,
        "mint": event.mint,
        "event_type": event.event_type,
        "reason": reason,
        "source": source,
        "schema_version": PING_PAYLOAD_SCHEMA_VERSION,
    })
    return "cand_" + _sha256_hex(material)[:24]


def _derive_ping_id(candidate: PrivatePreviewCandidate) -> str:
    material = _canonical_json({
        "candidate_id": candidate.candidate_id,
        "normalized_event_id": candidate.normalized_event_id,
        "mint": candidate.mint,
        "event_type": candidate.event_type,
        "stage": STAGE21_2_STAGE_LABEL,
        "visibility": PRIVATE_PREVIEW_VISIBILITY,
        "dispatch_target": FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
        "schema_version": PING_PAYLOAD_SCHEMA_VERSION,
    })
    return "ping_" + _sha256_hex(material)[:24]


def _derive_payload_hash(structured_payload: Mapping[str, object]) -> str:
    return _sha256_hex(_canonical_json(structured_payload))


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------


def build_candidate_from_normalized_event(
    event: NormalizedLiveEvent,
    *,
    reason: str = CANDIDATE_REASON_DEFAULT,
    source: str = CANDIDATE_SOURCE_DEFAULT,
) -> PrivatePreviewCandidate:
    """Build a ``PrivatePreviewCandidate`` from a normalized event.

    Pure: identical inputs produce identical output (including
    ``candidate_id``).

    Raises ``Stage21TelemetryError`` (E2113) on a non-event input
    or on empty reason / source strings.
    """
    if not isinstance(event, NormalizedLiveEvent):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "build_candidate_from_normalized_event expected "
                "NormalizedLiveEvent"
            ),
        )
    if not isinstance(reason, str) or reason == "":
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "build_candidate_from_normalized_event reason must be a "
                "non-empty str"
            ),
        )
    if not isinstance(source, str) or source == "":
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "build_candidate_from_normalized_event source must be a "
                "non-empty str"
            ),
        )
    # Stage 21.2 remediation (R11c): apply the shared safe_content
    # predicate to the caller-supplied reason and source before
    # constructing the candidate. Fields inherited from the
    # normalized event (mint / event_type / observed_at_utc /
    # normalized_event_id) were already validated upstream at the
    # normalizer boundary (R11b); they are re-validated below as
    # defense-in-depth after candidate construction.
    _sc.validate_safe_string(
        reason,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name="reason",
    )
    _sc.validate_safe_string(
        source,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name="source",
    )
    candidate_id = _derive_candidate_id(event, reason=reason, source=source)
    candidate = PrivatePreviewCandidate(
        candidate_id=candidate_id,
        normalized_event_id=event.event_id,
        mint=event.mint,
        event_type=event.event_type,
        observed_at_utc=event.observed_at_utc,
        reason=reason,
        source=source,
    )
    _sc.validate_safe_string(
        candidate.candidate_id,
        kind=_sc.SafeStringKind.SHORT_IDENTIFIER,
        field_name="candidate.candidate_id",
    )
    _sc.validate_safe_string(
        candidate.normalized_event_id,
        kind=_sc.SafeStringKind.SHORT_IDENTIFIER,
        field_name="candidate.normalized_event_id",
    )
    return candidate


# ---------------------------------------------------------------------------
# Ping payload construction
# ---------------------------------------------------------------------------


def _render_summary_text(candidate: PrivatePreviewCandidate) -> str:
    """Return the locked summary line for a Stage 21.2 private-preview ping.

    The summary is intentionally minimal and never embeds raw
    payload material. It includes the locked Stage 21.2 stage
    label and an operator-readable provenance fragment.
    """
    return (
        f"[Stage {STAGE21_2_STAGE_LABEL} private-preview] "
        f"{candidate.event_type} for {candidate.mint}"
    )


def _render_body_text(candidate: PrivatePreviewCandidate) -> str:
    """Return the locked body line for a Stage 21.2 private-preview ping."""
    return (
        f"candidate_id={candidate.candidate_id} "
        f"normalized_event_id={candidate.normalized_event_id} "
        f"observed_at_utc={candidate.observed_at_utc} "
        f"reason={candidate.reason} "
        f"source={candidate.source}"
    )


def _build_structured_payload(
    candidate: PrivatePreviewCandidate,
) -> Mapping[str, object]:
    """Return the locked structured payload mapping for a Stage 21.2 ping.

    Always carries the five locked marker fields plus a small
    provenance snapshot.  The returned mapping is a
    ``MappingProxyType`` so it cannot be mutated after
    construction.
    """
    payload: dict[str, object] = {
        "stage": STAGE21_2_STAGE_LABEL,
        "visibility": PRIVATE_PREVIEW_VISIBILITY,
        "operator_only": OPERATOR_ONLY_MARKER,
        "live_mode": LIVE_MODE_MARKER,
        "dispatch_target": FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
        "candidate_id": candidate.candidate_id,
        "normalized_event_id": candidate.normalized_event_id,
        "mint": candidate.mint,
        "event_type": candidate.event_type,
        "observed_at_utc": candidate.observed_at_utc,
        "reason": candidate.reason,
        "source": candidate.source,
        "schema_version": PING_PAYLOAD_SCHEMA_VERSION,
    }
    return MappingProxyType(payload)


def build_private_preview_payload(
    candidate: PrivatePreviewCandidate,
) -> PrivatePreviewPingPayload:
    """Build a ``PrivatePreviewPingPayload`` from a candidate.

    Pure: identical inputs produce identical output (including
    ``ping_id`` and ``payload_hash``).

    The constructed payload carries the locked Stage 21.2
    marker fields. ``assert_private_preview_markers`` is called
    before return so any drift surfaces as an error here rather
    than at the fake transport boundary.

    Raises ``Stage21TelemetryError`` (E2113) on a non-candidate
    input.
    """
    if not isinstance(candidate, PrivatePreviewCandidate):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "build_private_preview_payload expected "
                "PrivatePreviewCandidate"
            ),
        )
    structured_payload = _build_structured_payload(candidate)
    # Stage 21.2 remediation (R11d): apply the shared safe_content
    # predicate to the structured payload before hashing /
    # constructing the ping payload. Marker keys are passed via
    # exempt_keys because their values are exact-equality
    # enforced by assert_private_preview_markers below, which is
    # strictly stricter than any string predicate (and the locked
    # ``stage`` marker value ``"21.2"`` contains a literal ``.``
    # that would otherwise trip SHORT_LABEL).
    _sc.validate_safe_payload_dict(
        structured_payload,
        field_name="structured_payload",
        exempt_keys=frozenset(PING_PAYLOAD_REQUIRED_MARKER_KEYS),
    )
    payload_hash = _derive_payload_hash(structured_payload)
    ping = PrivatePreviewPingPayload(
        ping_id=_derive_ping_id(candidate),
        stage=STAGE21_2_STAGE_LABEL,
        visibility=PRIVATE_PREVIEW_VISIBILITY,
        operator_only=OPERATOR_ONLY_MARKER,
        live_mode=LIVE_MODE_MARKER,
        dispatch_target=FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
        candidate_id=candidate.candidate_id,
        normalized_event_id=candidate.normalized_event_id,
        mint=candidate.mint,
        event_type=candidate.event_type,
        observed_at_utc=candidate.observed_at_utc,
        summary_text=_render_summary_text(candidate),
        body_text=_render_body_text(candidate),
        structured_payload=structured_payload,
        payload_hash=payload_hash,
        schema_version=PING_PAYLOAD_SCHEMA_VERSION,
    )
    assert_private_preview_markers(ping)
    # Defense-in-depth: re-validate the constructed ping's
    # derived identifier fields after assembly. payload_hash is
    # validated as 64 lowercase hex via the payload-hash handler;
    # ping_id is validated as SHORT_IDENTIFIER.
    _sc.validate_safe_string(
        ping.ping_id,
        kind=_sc.SafeStringKind.SHORT_IDENTIFIER,
        field_name="ping.ping_id",
    )
    _sc.validate_payload_hash_value(
        ping.payload_hash,
        field_name="ping.payload_hash",
    )
    return ping


# ---------------------------------------------------------------------------
# Marker enforcement
# ---------------------------------------------------------------------------


def assert_private_preview_markers(payload: PrivatePreviewPingPayload) -> None:
    """Validate every locked marker on ``payload`` at exact equality.

    Stage 21.2 invariant: every private-preview ping MUST carry
    the five locked marker fields with the locked values. The
    check is exact-equality:

      * Boolean markers (``operator_only`` / ``live_mode``) are
        validated with ``is True`` / ``is False`` to reject
        truthy-but-non-bool values.
      * String markers are validated with ``==`` against the
        locked string constants.

    The structured payload mapping is also validated to carry
    the same marker key/value pairs so a payload that diverges
    between the named-tuple fields and the structured payload is
    rejected.

    Raises ``Stage21TelemetryError`` (E2110) when any required
    marker is missing or non-exact.
    Raises ``Stage21TelemetryError`` (E2111) when a marker value
    is present but does not match the locked value.
    """
    if not isinstance(payload, PrivatePreviewPingPayload):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2110,
            detail=(
                "assert_private_preview_markers expected "
                "PrivatePreviewPingPayload"
            ),
        )

    # Stage label
    if payload.stage != STAGE21_2_STAGE_LABEL:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2111,
            detail="ping payload stage marker does not match Stage 21.2 label",
        )
    # Visibility
    if payload.visibility != PRIVATE_PREVIEW_VISIBILITY:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2111,
            detail=(
                "ping payload visibility marker is not the locked "
                "private-preview value"
            ),
        )
    # Operator-only (strict bool identity)
    if payload.operator_only is not OPERATOR_ONLY_MARKER:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2111,
            detail="ping payload operator_only marker is not Python True",
        )
    # Live mode (strict bool identity)
    if payload.live_mode is not LIVE_MODE_MARKER:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2111,
            detail="ping payload live_mode marker is not Python False",
        )
    # Dispatch target
    if payload.dispatch_target != FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2111,
            detail=(
                "ping payload dispatch_target marker is not the locked "
                "fake-private-transport value"
            ),
        )

    # Structured payload markers
    structured = payload.structured_payload
    if not isinstance(structured, Mapping):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2110,
            detail=(
                "ping payload structured_payload must be a Mapping"
            ),
        )
    for key in PING_PAYLOAD_REQUIRED_MARKER_KEYS:
        if key not in structured:
            raise Stage21TelemetryError(
                Stage21ErrorCode.E2110,
                detail=(
                    f"ping payload structured_payload missing required "
                    f"marker key {key!r}"
                ),
            )
        expected = PING_PAYLOAD_REQUIRED_MARKER_VALUES[key]
        actual = structured[key]
        if key in ("operator_only", "live_mode"):
            # Identity check for booleans.
            if actual is not expected:
                raise Stage21TelemetryError(
                    Stage21ErrorCode.E2111,
                    detail=(
                        f"ping payload structured_payload marker {key!r} "
                        "is not the locked boolean value"
                    ),
                )
        else:
            if actual != expected:
                raise Stage21TelemetryError(
                    Stage21ErrorCode.E2111,
                    detail=(
                        f"ping payload structured_payload marker {key!r} "
                        "does not match the locked value"
                    ),
                )


__all__ = [
    "CANDIDATE_REASON_DEFAULT",
    "CANDIDATE_SOURCE_DEFAULT",
    "assert_private_preview_markers",
    "build_candidate_from_normalized_event",
    "build_private_preview_payload",
]
