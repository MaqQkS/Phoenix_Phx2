"""Stage 21.3A provider event decoder.

Pure decoder. Takes an opaque provider-supplied event payload
(a ``Mapping[str, object]`` produced upstream of any Stage 21.3A
boundary) and constructs a ``NormalizedLiveEvent`` directly.

Per locked operator decision Q1 the decoder does NOT delegate to
``normalize_fake_event`` and does NOT modify
``PHX2/stage21/normalized_events.py``. The decoder constructs
the ``NormalizedLiveEvent`` NamedTuple directly so the Stage
21.2 fake-only constraints (locked fake provider name / fake
chain / fake event-type vocabulary) do not apply to real
provider input.

Per locked operator decision Q2 the Stage 21.3A
``SUPPORTED_INSTRUCTION_KINDS`` is the placeholder
``frozenset({"reserved_for_21_3b"})``. The real PumpSwap / Pump.fun
instruction-kind vocabulary lands in Stage 21.3B+; Stage 21.3A
does not guess it.

Per locked operator decision Q3 the decoder uses a module-local
error hierarchy rooted at ``ProviderPayloadError``. It does NOT
modify ``errors.py`` or the central Stage 21 error-code
registry; the closed-set Stage 21 E2120..E2122 codes are
reserved for the Stage 21.3B+ real adapter contract surface.

Per locked operator decision Q9 the suspicious-content scan
walks string-typed top-level fields and the top level of
``decoded_fields`` only. It does NOT recurse into nested
mappings or sequences beneath ``decoded_fields``, and it does
NOT add entropy / hex / base58 heuristics. A legitimate Solana
signature (a ~88-char base58 string) must not trigger this
scan. The substring set is the locked
``PHX2.stage21.constants.FORBIDDEN_SUBSTRINGS`` (URL-scheme
prefixes, colon-slash-slash, webhook, api_key, secret,
password, credential, public_dispatch, paid_dispatch,
subscriber).

This module imports no network library, opens no socket, reads
no environment variable, and depends on no Phoenix1 / prior
Stage 17..20 module.
"""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from PHX2.stage21.constants import FORBIDDEN_SUBSTRINGS
from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage21.ping_payloads import NORMALIZED_EVENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Locked Stage 21.3A vocabulary
# ---------------------------------------------------------------------------


# Per locked operator decision Q2. The placeholder kind is the
# only value the decoder accepts in Stage 21.3A. Tests use the
# same placeholder string as the only valid ``instruction_kind``
# input. The real vocabulary lands in Stage 21.3B with the
# concrete adapter.
SUPPORTED_INSTRUCTION_KINDS: frozenset[str] = frozenset(
    {"reserved_for_21_3b"},
)


# ---------------------------------------------------------------------------
# Module-local error hierarchy (per locked operator decision Q3)
# ---------------------------------------------------------------------------


class ProviderPayloadError(Exception):
    """Base error for Stage 21.3A provider event decoder violations.

    Module-local hierarchy; intentionally not a subclass of
    ``Stage21Error`` so the closed Stage 21 E2120..E2122 codes
    remain reserved for the Stage 21.3B+ real adapter contract.
    """


class ProviderPayloadShapeError(ProviderPayloadError):
    """Raised when the payload root is not a Mapping or required keys are missing."""


class ProviderPayloadFieldTypeError(ProviderPayloadError):
    """Raised when a required field has the wrong Python type."""


class ProviderPayloadFieldValueError(ProviderPayloadError):
    """Raised when a required field has an invalid value (empty, negative, ...)."""


class ProviderPayloadUnsupportedInstructionError(ProviderPayloadError):
    """Raised when instruction_kind is outside SUPPORTED_INSTRUCTION_KINDS."""


class ProviderPayloadSuspiciousContentError(ProviderPayloadError):
    """Raised when a scanned string contains a forbidden routing/credential substring."""


# ---------------------------------------------------------------------------
# Required-key surface
# ---------------------------------------------------------------------------
#
# These are the keys the decoder reads from the payload. The
# concrete provider adapter (Stage 21.3B+) is responsible for
# producing this exact shape from whatever upstream format it
# receives -- the decoder is the boundary that accepts only this
# shape.


REQUIRED_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "provider_event_id",
    "provider_name",
    "source_kind",
    "chain",
    "mint",
    "event_type",
    "observed_at_utc",
    "slot",
    "signature",
    "instruction_kind",
    "decoded_fields",
)


# Top-level string fields scanned for forbidden substrings.
# Per Q9 the scan covers string-typed values; ``slot`` (int)
# and ``decoded_fields`` (mapping) are excluded from this list.
_STRING_FIELDS_SCANNED: tuple[str, ...] = (
    "provider_event_id",
    "provider_name",
    "source_kind",
    "chain",
    "mint",
    "event_type",
    "observed_at_utc",
    "signature",
    "instruction_kind",
)


# ---------------------------------------------------------------------------
# Type / value guards
# ---------------------------------------------------------------------------


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise ProviderPayloadFieldTypeError(
            f"field {key!r} must be str; got {type(value).__name__}"
        )
    if value == "":
        raise ProviderPayloadFieldValueError(
            f"field {key!r} must be a non-empty string"
        )
    return value


def _require_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload[key]
    # bool is a subclass of int in Python; reject it explicitly
    # so a stray True/False slot does not silently coerce to 1/0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProviderPayloadFieldTypeError(
            f"field {key!r} must be int; got {type(value).__name__}"
        )
    if value < 0:
        raise ProviderPayloadFieldValueError(
            f"field {key!r} must be non-negative"
        )
    return value


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload[key]
    if not isinstance(value, Mapping):
        raise ProviderPayloadFieldTypeError(
            f"field {key!r} must be Mapping; got {type(value).__name__}"
        )
    return value


# ---------------------------------------------------------------------------
# Suspicious-content scan (per Q9)
# ---------------------------------------------------------------------------


def _scan_for_forbidden_substring(value: str, *, field_label: str) -> None:
    """Reject a string value that contains any locked forbidden substring.

    Per locked operator decision Q9 the scan walks only:
      * string-typed top-level fields, and
      * string values inside ``decoded_fields`` at the top level
        of that mapping (no recursion).

    The scan does NOT add entropy / hex / base58 heuristics; a
    legitimate Solana signature (~88-char base58 string) must not
    trigger this check.

    The forbidden substring set is
    ``PHX2.stage21.constants.FORBIDDEN_SUBSTRINGS`` (the locked
    Stage 21.2 R4 set: URL-scheme prefixes, colon-slash-slash,
    webhook, api_key, secret, password, credential,
    public_dispatch, paid_dispatch, subscriber).
    """
    lower = value.lower()
    for sub in FORBIDDEN_SUBSTRINGS:
        if sub in lower:
            raise ProviderPayloadSuspiciousContentError(
                f"field {field_label!r} contains forbidden substring "
                f"{sub!r}"
            )


# ---------------------------------------------------------------------------
# Deterministic id derivation
# ---------------------------------------------------------------------------


def _to_plain(value: object) -> object:
    """Convert mappings / tuples to plain dict / list for JSON encoding."""
    if isinstance(value, Mapping):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _canonical_json(payload: object) -> str:
    """Return canonical JSON of ``payload`` with sorted keys, no whitespace."""
    return json.dumps(
        _to_plain(payload),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _sha256_hex(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _derive_raw_event_hash(
    *,
    provider_name: str,
    provider_event_id: str,
    event_type: str,
    mint: str,
    chain: str,
    slot: int,
    signature: str,
    observed_at_utc: str,
    decoded_fields: Mapping[str, Any],
    instruction_kind: str,
) -> str:
    """Derive the deterministic raw_event_hash for a real provider event.

    The hash is sha256 of the canonical JSON encoding of the
    identifying fields plus the decoded fields and the
    instruction kind. The instruction kind is included so two
    events that differ only in instruction_kind produce distinct
    raw_event_hash values.
    """
    material = _canonical_json({
        "provider_name": provider_name,
        "provider_event_id": provider_event_id,
        "event_type": event_type,
        "mint": mint,
        "chain": chain,
        "slot": slot,
        "signature": signature,
        "observed_at_utc": observed_at_utc,
        "decoded_fields": decoded_fields,
        "instruction_kind": instruction_kind,
    })
    return _sha256_hex(material)


def _derive_event_id(
    *,
    provider_name: str,
    provider_event_id: str,
    raw_event_hash: str,
    chain: str,
    mint: str,
) -> str:
    """Derive the Stage 21 normalized event_id (``"evt_<24 hex>"``).

    Mirrors the Stage 21.2 derivation shape so the
    ``NormalizedLiveEvent.event_id`` namespace is consistent
    across fake and real producers.
    """
    material = _canonical_json({
        "provider_name": provider_name,
        "provider_event_id": provider_event_id,
        "raw_event_hash": raw_event_hash,
        "chain": chain,
        "mint": mint,
        "schema_version": NORMALIZED_EVENT_SCHEMA_VERSION,
    })
    return "evt_" + _sha256_hex(material)[:24]


# ---------------------------------------------------------------------------
# Frozen payload summary
# ---------------------------------------------------------------------------


def _freeze_value(value: object) -> object:
    """Recursively freeze a payload value for storage in payload_summary."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(k): _freeze_value(v) for k, v in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(v) for v in value)
    return value


def _freeze_payload_summary(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a deeply-frozen ``MappingProxyType`` snapshot of ``raw``."""
    return MappingProxyType(
        {str(k): _freeze_value(v) for k, v in raw.items()}
    )


# ---------------------------------------------------------------------------
# Public decoder
# ---------------------------------------------------------------------------


def decode_provider_event(payload: Mapping[str, Any]) -> NormalizedLiveEvent:
    """Decode a provider-supplied event payload into a ``NormalizedLiveEvent``.

    Pure function; no I/O. Raises one of the
    ``ProviderPayloadError`` subclasses on any contract violation
    and otherwise returns the constructed ``NormalizedLiveEvent``
    with a frozen ``payload_summary``.

    Validation order (each step raises immediately on failure):
      1. Root must be a Mapping (else
         ``ProviderPayloadShapeError``).
      2. Every key in ``REQUIRED_TOP_LEVEL_KEYS`` must be
         present (else ``ProviderPayloadShapeError`` naming the
         missing key).
      3. Each typed field must satisfy its type / value guard
         (else ``ProviderPayloadFieldTypeError`` /
         ``ProviderPayloadFieldValueError``).
      4. ``instruction_kind`` must be in
         ``SUPPORTED_INSTRUCTION_KINDS`` (else
         ``ProviderPayloadUnsupportedInstructionError``).
      5. Each scanned top-level string field is checked against
         the locked ``FORBIDDEN_SUBSTRINGS`` set, then each
         string value at the top level of ``decoded_fields`` is
         checked the same way (else
         ``ProviderPayloadSuspiciousContentError`` naming the
         field and matched substring).

    Returns a ``NormalizedLiveEvent`` carrying:
      * ``event_id`` derived deterministically from the
        identifying fields,
      * ``raw_event_hash`` derived deterministically from the
        full payload material plus the instruction kind,
      * ``normalized_schema_version`` set to the locked
        ``NORMALIZED_EVENT_SCHEMA_VERSION``,
      * ``payload_summary`` set to a deeply-frozen
        ``MappingProxyType`` snapshot of ``decoded_fields``.

    Identical input produces identical output (pure /
    deterministic).
    """
    if not isinstance(payload, Mapping):
        raise ProviderPayloadShapeError(
            "payload must be a Mapping; got "
            f"{type(payload).__name__}"
        )

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in payload:
            raise ProviderPayloadShapeError(
                f"payload missing required key {key!r}"
            )

    provider_event_id = _require_str(payload, "provider_event_id")
    provider_name = _require_str(payload, "provider_name")
    source_kind = _require_str(payload, "source_kind")
    chain = _require_str(payload, "chain")
    mint = _require_str(payload, "mint")
    event_type = _require_str(payload, "event_type")
    observed_at_utc = _require_str(payload, "observed_at_utc")
    slot = _require_int(payload, "slot")
    signature = _require_str(payload, "signature")
    instruction_kind = _require_str(payload, "instruction_kind")
    decoded_fields = _require_mapping(payload, "decoded_fields")

    if instruction_kind not in SUPPORTED_INSTRUCTION_KINDS:
        # AUDIT-21.3A-M2: the exception message MUST NOT echo the
        # raw ``instruction_kind`` value. A provider can supply
        # any string here -- including a secret-like or
        # URL-shaped value -- and the suspicious-content scan
        # runs after this check, so a raw echo would leak the
        # value before sanitization. The message names only the
        # field (a constant from REQUIRED_TOP_LEVEL_KEYS); the
        # raw value never enters the formatted detail.
        raise ProviderPayloadUnsupportedInstructionError(
            "unknown instruction kind for field 'instruction_kind'"
        )

    # Suspicious-content scan -- Q9 scope: string-typed top-level
    # fields, plus string values inside decoded_fields at the top
    # level of that mapping. No recursion beneath decoded_fields.
    scanned_top: dict[str, str] = {
        "provider_event_id": provider_event_id,
        "provider_name": provider_name,
        "source_kind": source_kind,
        "chain": chain,
        "mint": mint,
        "event_type": event_type,
        "observed_at_utc": observed_at_utc,
        "signature": signature,
        "instruction_kind": instruction_kind,
    }
    for field_name in _STRING_FIELDS_SCANNED:
        _scan_for_forbidden_substring(
            scanned_top[field_name],
            field_label=field_name,
        )

    for df_key, df_value in decoded_fields.items():
        if isinstance(df_value, str):
            _scan_for_forbidden_substring(
                df_value,
                field_label=f"decoded_fields.{df_key}",
            )

    raw_event_hash = _derive_raw_event_hash(
        provider_name=provider_name,
        provider_event_id=provider_event_id,
        event_type=event_type,
        mint=mint,
        chain=chain,
        slot=slot,
        signature=signature,
        observed_at_utc=observed_at_utc,
        decoded_fields=decoded_fields,
        instruction_kind=instruction_kind,
    )
    event_id = _derive_event_id(
        provider_name=provider_name,
        provider_event_id=provider_event_id,
        raw_event_hash=raw_event_hash,
        chain=chain,
        mint=mint,
    )
    payload_summary = _freeze_payload_summary(decoded_fields)

    return NormalizedLiveEvent(
        event_id=event_id,
        provider_event_id=provider_event_id,
        provider_name=provider_name,
        source_kind=source_kind,
        chain=chain,
        mint=mint,
        event_type=event_type,
        observed_at_utc=observed_at_utc,
        slot=slot,
        signature=signature,
        raw_event_hash=raw_event_hash,
        normalized_schema_version=NORMALIZED_EVENT_SCHEMA_VERSION,
        payload_summary=payload_summary,
    )


__all__ = [
    "ProviderPayloadError",
    "ProviderPayloadFieldTypeError",
    "ProviderPayloadFieldValueError",
    "ProviderPayloadShapeError",
    "ProviderPayloadSuspiciousContentError",
    "ProviderPayloadUnsupportedInstructionError",
    "REQUIRED_TOP_LEVEL_KEYS",
    "SUPPORTED_INSTRUCTION_KINDS",
    "decode_provider_event",
]
