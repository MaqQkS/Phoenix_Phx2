"""Stage 27.5 private ping provenance artifact builder.

Pure / deterministic builder that turns a Stage 27.5
``PrivatePingPayloadRecord`` into a Stage 27.5
``PingProvenanceArtifactRecord``. The provenance artifact is a
redacted summary record describing that a dry-run ping was produced.
It is NEVER itself a Discord payload, NEVER carries a raw provider
payload blob, NEVER carries a secret, a webhook URL, an RPC URL, or
any Stage 26 enforcement decision.

The deterministic content hash is computed over a canonical JSON
encoding of the payload (every byte the artifact writer will
persist). The artifact-created-at timestamp is supplied by an
injected ``Stage27_5Clock`` Protocol; Stage 27.5 NEVER calls
``datetime.now()`` / ``time.time()`` directly.

This module imports only stdlib (``hashlib`` / ``json`` / ``typing``)
plus Stage 27.5 production modules. It does NOT import Stage 21-26
production code, does NOT import Stage 27.1 production code, does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process environment,
does NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Protocol

from PHX2.stage27.private_ping_models import (
    ARTIFACT_KIND_PRIVATE_PING_DRY_RUN,
    PingProvenanceArtifactRecord,
    PrivatePingPayloadRecord,
    REDACTION_STATUS_REDACTED,
    STAGE27_5_PING_SCHEMA_VERSION,
    STAGE27_5_PROVENANCE_SCHEMA_VERSION,
    is_forbidden_payload_field_name,
)


# ---------------------------------------------------------------------------
# Injected clock Protocol
# ---------------------------------------------------------------------------


class Stage27_5Clock(Protocol):
    """Injected clock for Stage 27.5 provenance / artifact wall time.

    Stage 27.5 NEVER calls ``datetime.now()`` / ``time.time()``
    directly. Every wall-time read flows through this Protocol so
    tests can pin an exact ISO-8601 UTC string deterministically.
    """

    def now_utc_iso(self) -> str:
        """Return the current wall time as an ISO-8601 UTC string."""
        ...


# ---------------------------------------------------------------------------
# Deterministic payload-content hash
# ---------------------------------------------------------------------------


def _canonical_payload_mapping(
    payload: PrivatePingPayloadRecord,
) -> Mapping[str, object]:
    """Return the canonical JSON-shaped mapping for ``payload``.

    Lists rather than tuples are used so ``json.dumps`` produces
    identical bytes regardless of caller-side iterable type.
    """
    return {
        "ping_id": payload.ping_id,
        "run_id": payload.run_id,
        "session_id": payload.session_id,
        "ping_schema_version": payload.ping_schema_version,
        "provider_id": payload.provider_id,
        "provider_event_id": payload.provider_event_id,
        "normalized_event_id": payload.normalized_event_id,
        "raw_capture_ref": payload.raw_capture_ref,
        "token_mint": payload.token_mint,
        "quote_mint": payload.quote_mint,
        "pair_type": payload.pair_type,
        "quote_asset": payload.quote_asset,
        "bonding_curve_version": payload.bonding_curve_version,
        "pair_detection_status": payload.pair_detection_status,
        "pair_detection_confidence": (
            payload.pair_detection_confidence
        ),
        "pair_detection_reason": payload.pair_detection_reason,
        "pair_live_policy": payload.pair_live_policy,
        "calibration_lane": payload.calibration_lane,
        "measurement_status": payload.measurement_status,
        "measurement_warnings": list(payload.measurement_warnings),
        "price_status": payload.price_status,
        "price_value_display": payload.price_value_display,
        "price_unit_display": payload.price_unit_display,
        "price_source_display": payload.price_source_display,
        "price_staleness_seconds_display": (
            payload.price_staleness_seconds_display
        ),
        "ath_status": payload.ath_status,
        "ath_value_display": payload.ath_value_display,
        "ath_unit_display": payload.ath_unit_display,
        "ath_since_migration_status_display": (
            payload.ath_since_migration_status_display
        ),
        "drawdown_display": payload.drawdown_display,
        "drawdown_basis_display": payload.drawdown_basis_display,
        "migration_status": payload.migration_status,
        "migration_timestamp_display": (
            payload.migration_timestamp_display
        ),
        "migration_age_seconds_display": (
            payload.migration_age_seconds_display
        ),
        "migration_source_display": (
            payload.migration_source_display
        ),
        "render_status": payload.render_status,
        "render_note": payload.render_note,
        "body_text": payload.body_text,
    }


def canonical_payload_json(
    payload: PrivatePingPayloadRecord,
) -> str:
    """Return the canonical JSON encoding of ``payload``.

    Stable across runs:

      * ``sort_keys=True``,
      * ``separators=(",", ":")`` (no incidental whitespace),
      * UTF-8 friendly (``ensure_ascii=False``).

    Pure / deterministic.
    """
    if not isinstance(payload, PrivatePingPayloadRecord):
        raise TypeError(
            "canonical_payload_json requires a "
            "PrivatePingPayloadRecord"
        )
    mapping = _canonical_payload_mapping(payload)
    return json.dumps(
        mapping,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_payload_content_hash(
    payload: PrivatePingPayloadRecord,
) -> str:
    """Return the SHA-256 hex digest of the canonical payload JSON.

    Pure / deterministic. Two identical payloads always produce
    identical hex digests.
    """
    encoded = canonical_payload_json(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# Redaction sweep (defensive)
# ---------------------------------------------------------------------------


def _redaction_sweep_payload(
    payload: PrivatePingPayloadRecord,
) -> str:
    """Return ``REDACTION_STATUS_REDACTED`` iff no forbidden field-name
    substring appears in any payload field.

    The Stage 27.5 ``NamedTuple`` schema already excludes raw-payload
    / secret / webhook fields; the sweep below is defensive against
    a future refactor that silently widens the admitted shape.
    """
    for field_name in payload._fields:
        if is_forbidden_payload_field_name(field_name):
            return "REDACTION_FAILED"
    return REDACTION_STATUS_REDACTED


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_ping_provenance_artifact(
    payload: PrivatePingPayloadRecord,
    clock: Stage27_5Clock,
) -> PingProvenanceArtifactRecord:
    """Return the Stage 27.5 provenance artifact for ``payload``.

    Pure / deterministic except for the injected ``clock.now_utc_iso()``
    read. NEVER opens a network connection, NEVER reads the process
    environment, NEVER deduplicates events, NEVER enforces Stage 26
    policy candidates, NEVER decides a trading verdict.
    """
    if not isinstance(payload, PrivatePingPayloadRecord):
        raise TypeError(
            "build_ping_provenance_artifact requires a "
            "PrivatePingPayloadRecord"
        )
    created_at = clock.now_utc_iso()
    if not isinstance(created_at, str) or created_at == "":
        raise ValueError(
            "Stage27_5Clock.now_utc_iso must return a non-empty "
            "ISO-8601 UTC string"
        )

    content_hash = compute_payload_content_hash(payload)
    redaction_status = _redaction_sweep_payload(payload)

    return PingProvenanceArtifactRecord(
        artifact_kind=ARTIFACT_KIND_PRIVATE_PING_DRY_RUN,
        artifact_schema_version=(
            STAGE27_5_PROVENANCE_SCHEMA_VERSION
        ),
        artifact_created_at_utc=created_at,
        ping_id=payload.ping_id,
        ping_schema_version=STAGE27_5_PING_SCHEMA_VERSION,
        run_id=payload.run_id,
        session_id=payload.session_id,
        provider_id=payload.provider_id,
        provider_event_id=payload.provider_event_id,
        normalized_event_id=payload.normalized_event_id,
        raw_capture_ref=payload.raw_capture_ref,
        token_mint=payload.token_mint,
        pair_quote_asset=payload.quote_asset,
        pair_type=payload.pair_type,
        pair_detection_status=payload.pair_detection_status,
        pair_detection_confidence=(
            payload.pair_detection_confidence
        ),
        pair_live_policy=payload.pair_live_policy,
        calibration_lane=payload.calibration_lane,
        measurement_status=payload.measurement_status,
        measurement_warnings=tuple(payload.measurement_warnings),
        render_status=payload.render_status,
        redaction_status=redaction_status,
        payload_content_hash=content_hash,
    )


# ---------------------------------------------------------------------------
# Canonical artifact JSON (used by the writer)
# ---------------------------------------------------------------------------


def canonical_artifact_json(
    artifact: PingProvenanceArtifactRecord,
) -> str:
    """Return the canonical JSON encoding of a provenance artifact.

    Pure / deterministic. Stable key ordering. UTF-8 friendly. No
    incidental whitespace.
    """
    if not isinstance(artifact, PingProvenanceArtifactRecord):
        raise TypeError(
            "canonical_artifact_json requires a "
            "PingProvenanceArtifactRecord"
        )
    mapping = {
        "artifact_kind": artifact.artifact_kind,
        "artifact_schema_version": (
            artifact.artifact_schema_version
        ),
        "artifact_created_at_utc": (
            artifact.artifact_created_at_utc
        ),
        "ping_id": artifact.ping_id,
        "ping_schema_version": artifact.ping_schema_version,
        "run_id": artifact.run_id,
        "session_id": artifact.session_id,
        "provider_id": artifact.provider_id,
        "provider_event_id": artifact.provider_event_id,
        "normalized_event_id": artifact.normalized_event_id,
        "raw_capture_ref": artifact.raw_capture_ref,
        "token_mint": artifact.token_mint,
        "pair_quote_asset": artifact.pair_quote_asset,
        "pair_type": artifact.pair_type,
        "pair_detection_status": artifact.pair_detection_status,
        "pair_detection_confidence": (
            artifact.pair_detection_confidence
        ),
        "pair_live_policy": artifact.pair_live_policy,
        "calibration_lane": artifact.calibration_lane,
        "measurement_status": artifact.measurement_status,
        "measurement_warnings": list(
            artifact.measurement_warnings
        ),
        "render_status": artifact.render_status,
        "redaction_status": artifact.redaction_status,
        "payload_content_hash": artifact.payload_content_hash,
    }
    return json.dumps(
        mapping,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
