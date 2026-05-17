"""Stage 21.2 private-preview candidate and ping payload models.

Stage 21.2 builds the first fully local fake private live-path
simulation: fake provider event -> normalized event -> private
preview candidate -> private preview ping payload -> fake private
transport capture -> file artifacts.

This module declares the locked Stage 21.2 marker constants and
the two typed payload records that every fake-only ping must
carry:

  * ``PrivatePreviewCandidate`` -- the tiny intermediate produced
    by mapping a ``NormalizedLiveEvent`` into a per-event,
    operator-only candidate.
  * ``PrivatePreviewPingPayload`` -- the final ping handed to the
    fake transport. Carries the locked private-preview marker
    fields (stage / visibility / operator_only / live_mode /
    dispatch_target), the candidate provenance, the rendered
    summary + body, the structured payload, and a deterministic
    ``payload_hash``.

The Stage 21.2 fake transport asserts the ping carries the locked
markers at exact-equality before it captures anything; this
matches the Stage 21.1 transport-contract dispatch-safety check
pattern. Stage 21.2 ships only the fake-only contract surface;
no real transport or live dispatch is introduced.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, NamedTuple


# ---------------------------------------------------------------------------
# Stage 21.2 locked marker constants
# ---------------------------------------------------------------------------


# Stage label string embedded in every Stage 21.2 ping payload.
# Kept as a local Stage 21.2 constant rather than reusing the
# Stage 21.1 ``STAGE21_MINOR_VERSION`` so the Stage 21.1
# foundation invariants (and tests that pin
# ``STAGE21_MINOR_VERSION == "21.1"``) remain untouched.
STAGE21_2_STAGE_LABEL: str = "21.2"

# Locked visibility marker. Every Stage 21.2 ping payload carries
# this exact string in the ``visibility`` field. The fake
# transport rejects any non-exact value.
PRIVATE_PREVIEW_VISIBILITY: str = "private_preview"

# Locked operator-only marker. Boolean ``True`` (literal Python
# ``True``). The fake transport asserts identity-with-True so a
# truthy-but-not-True value (e.g. ``1`` / ``"yes"``) is rejected.
OPERATOR_ONLY_MARKER: bool = True

# Locked live-mode marker. Boolean ``False`` (literal Python
# ``False``). Stage 21.2 is fake-only; any True value indicates
# the caller flipped the per-payload flag locally and must be
# rejected at the transport boundary.
LIVE_MODE_MARKER: bool = False

# Locked dispatch target marker. The Stage 21.2 fake transport
# is the only legal target for a Stage 21.2 ping. The string
# value is intentionally not a URL, not a credentialed identifier,
# and not a public/paid/subscriber routing identifier.
FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET: str = "fake_private_transport"

# Locked normalized-event schema version. Embedded in every
# normalized event so the consumer can pin the shape.
NORMALIZED_EVENT_SCHEMA_VERSION: str = "stage21_2_normalized_event_v0"

# Locked ping payload schema version. Embedded in every ping
# payload so the consumer can pin the shape.
PING_PAYLOAD_SCHEMA_VERSION: str = "stage21_2_ping_payload_v0"

# Stage 21.2 fake provider name. Reserved Stage-21-owned name.
# Used by the fake provider as its ``provider_name`` so the
# normalized event downstream can verify provenance.
STAGE21_FAKE_PROVIDER_NAME: str = "stage21_fake_provider"

# Stage 21.2 fake chain identifier. Reserved Stage-21-owned name.
# Used by the fake provider so the normalized event chain field
# is identifiable as fake-only.
STAGE21_FAKE_CHAIN_NAME: str = "stage21_fake_chain"

# Stage 21.2 fake source kind. Reserved Stage-21-owned name.
STAGE21_FAKE_SOURCE_KIND: str = "stage21_fake_source"

# Required marker keys that every Stage 21.2 ping payload's
# structured payload mapping MUST carry. Used by the ping
# builder and the fake transport for exact-equality checks.
PING_PAYLOAD_REQUIRED_MARKER_KEYS: tuple[str, ...] = (
    "stage",
    "visibility",
    "operator_only",
    "live_mode",
    "dispatch_target",
)

# Required exact-equality marker values keyed by marker name.
# The fake transport iterates this mapping to assert each
# payload field matches its locked value.
PING_PAYLOAD_REQUIRED_MARKER_VALUES: Mapping[str, object] = MappingProxyType({
    "stage": STAGE21_2_STAGE_LABEL,
    "visibility": PRIVATE_PREVIEW_VISIBILITY,
    "operator_only": OPERATOR_ONLY_MARKER,
    "live_mode": LIVE_MODE_MARKER,
    "dispatch_target": FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
})


# ---------------------------------------------------------------------------
# Stage 21.2 typed payload records
# ---------------------------------------------------------------------------


class PrivatePreviewCandidate(NamedTuple):
    """Tiny private-preview candidate produced from a normalized event.

    Fields:
      * ``candidate_id`` -- deterministic Stage 21.2 candidate id
        derived by the ping builder from the normalized event.
      * ``normalized_event_id`` -- provenance pointer back to the
        normalized event the candidate was built from.
      * ``mint`` -- mint identifier copied from the normalized event.
      * ``event_type`` -- event-type label copied from the
        normalized event.
      * ``observed_at_utc`` -- ISO-8601 UTC string copied from the
        normalized event's ``observed_at_utc`` field.
      * ``reason`` -- short non-secret reason string the ping
        builder set when promoting the event into a candidate.
      * ``source`` -- short non-secret source label (Stage 21-owned
        identifier such as ``"stage21_fake_provider_normalized"``).
    """

    candidate_id: str
    normalized_event_id: str
    mint: str
    event_type: str
    observed_at_utc: str
    reason: str
    source: str

    def public_summary(self) -> Mapping[str, object]:
        """Return a manifest-safe dict view of the candidate."""
        return {
            "candidate_id": self.candidate_id,
            "normalized_event_id": self.normalized_event_id,
            "mint": self.mint,
            "event_type": self.event_type,
            "observed_at_utc": self.observed_at_utc,
            "reason": self.reason,
            "source": self.source,
        }


class PrivatePreviewPingPayload(NamedTuple):
    """Locked Stage 21.2 private-preview ping payload.

    Carries:
      * ``ping_id`` -- deterministic Stage 21.2 ping id derived
        from the candidate.
      * ``stage`` -- locked Stage 21.2 stage label string
        (``"21.2"``). Exact-equality required by the fake
        transport.
      * ``visibility`` -- locked ``"private_preview"`` string.
      * ``operator_only`` -- locked ``True`` boolean.
      * ``live_mode`` -- locked ``False`` boolean.
      * ``dispatch_target`` -- locked
        ``"fake_private_transport"`` string.
      * ``candidate_id`` / ``normalized_event_id`` -- provenance
        pointers.
      * ``mint`` / ``event_type`` / ``observed_at_utc`` -- event
        provenance fields copied through.
      * ``summary_text`` -- short non-secret operator-visible
        summary line.
      * ``body_text`` -- longer non-secret operator-visible body.
      * ``structured_payload`` -- frozen
        ``MappingProxyType[str, object]`` carrying the marker
        fields plus copied event provenance. The fake transport
        re-asserts the marker fields against this mapping.
      * ``payload_hash`` -- deterministic sha256 hex of the
        canonical JSON-encoded ``structured_payload``.
      * ``schema_version`` -- locked Stage 21.2 ping payload
        schema version string.
    """

    ping_id: str
    stage: str
    visibility: str
    operator_only: bool
    live_mode: bool
    dispatch_target: str
    candidate_id: str
    normalized_event_id: str
    mint: str
    event_type: str
    observed_at_utc: str
    summary_text: str
    body_text: str
    structured_payload: Mapping[str, object]
    payload_hash: str
    schema_version: str

    def public_summary(self) -> Mapping[str, object]:
        """Return a manifest-safe dict view of the ping payload.

        The structured payload is materialized to a plain dict so
        the JSON writer can serialize it; the underlying
        ``MappingProxyType`` instance is read-only and JSON-
        serializable through ``dict()``.
        """
        return {
            "ping_id": self.ping_id,
            "stage": self.stage,
            "visibility": self.visibility,
            "operator_only": self.operator_only,
            "live_mode": self.live_mode,
            "dispatch_target": self.dispatch_target,
            "candidate_id": self.candidate_id,
            "normalized_event_id": self.normalized_event_id,
            "mint": self.mint,
            "event_type": self.event_type,
            "observed_at_utc": self.observed_at_utc,
            "summary_text": self.summary_text,
            "body_text": self.body_text,
            "structured_payload": dict(self.structured_payload),
            "payload_hash": self.payload_hash,
            "schema_version": self.schema_version,
        }


__all__ = [
    "FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET",
    "LIVE_MODE_MARKER",
    "NORMALIZED_EVENT_SCHEMA_VERSION",
    "OPERATOR_ONLY_MARKER",
    "PING_PAYLOAD_REQUIRED_MARKER_KEYS",
    "PING_PAYLOAD_REQUIRED_MARKER_VALUES",
    "PING_PAYLOAD_SCHEMA_VERSION",
    "PRIVATE_PREVIEW_VISIBILITY",
    "PrivatePreviewCandidate",
    "PrivatePreviewPingPayload",
    "STAGE21_2_STAGE_LABEL",
    "STAGE21_FAKE_CHAIN_NAME",
    "STAGE21_FAKE_PROVIDER_NAME",
    "STAGE21_FAKE_SOURCE_KIND",
]
